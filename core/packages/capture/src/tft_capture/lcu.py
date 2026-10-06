"""League client API (LCU): find the client and follow its gameflow phase.

The port and token come from `LeagueClientUx.exe`'s command line. The watcher
subscribes to gameflow phase events on the client's WebSocket and falls back
to polling the phase over HTTPS while the subscription is down. It copes with
the client not running, starting late, restarting and exiting.

The token authenticates to the local client only. It never goes to a log.
"""

import asyncio
import base64
import json
import logging
import ssl
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol

import httpx
import psutil
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import WebSocketException

log = logging.getLogger(__name__)

CLIENT_PROCESS = "LeagueClientUx.exe"
PHASE_PATH = "/lol-gameflow/v1/gameflow-phase"
PHASE_EVENT = "OnJsonApiEvent_lol-gameflow_v1_gameflow-phase"
_WAMP_SUBSCRIBE = 5
_WAMP_EVENT = 8


@dataclass(frozen=True)
class LcuCredentials:
    port: int
    token: str = field(repr=False)


@dataclass(frozen=True)
class GameflowUpdate:
    """The client's state: running or not, and its phase (None when it has none)."""

    client_running: bool
    phase: str | None
    game_id: str | None = None


NOT_RUNNING = GameflowUpdate(client_running=False, phase=None)


class LcuUnavailable(Exception):
    """The client stopped answering; find it again."""


class SubscribeFailed(Exception):
    """The event WebSocket is down; poll instead."""


# Parsing.


def parse_command_line(args: Sequence[str]) -> LcuCredentials | None:
    """Read `--app-port` and `--remoting-auth-token` from the client's arguments."""
    values: dict[str, str] = {}
    for arg in args:
        name, sep, value = arg.strip('"').partition("=")
        if sep and name in ("--app-port", "--remoting-auth-token"):
            values[name] = value.strip('"')
    port, token = values.get("--app-port"), values.get("--remoting-auth-token")
    if not port or not token or not port.isdigit():
        return None
    return LcuCredentials(port=int(port), token=token)


def parse_phase(body: str | bytes) -> str | None:
    """Parse the body of GET /lol-gameflow/v1/gameflow-phase, a JSON string such as "Lobby"."""
    value = json.loads(body)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"unexpected gameflow phase body: {value!r}")
    return value


_NOT_A_PHASE_EVENT = object()


def parse_phase_event(raw: str | bytes) -> object:
    """Parse one WAMP frame from the client's WebSocket.

    Returns the new phase (None when the phase was deleted), or
    `_NOT_A_PHASE_EVENT` for any other frame.
    """
    try:
        frame = json.loads(raw)
    except ValueError:
        return _NOT_A_PHASE_EVENT
    if not (
        isinstance(frame, list)
        and len(frame) == 3
        and frame[0] == _WAMP_EVENT
        and frame[1] == PHASE_EVENT
        and isinstance(frame[2], dict)
    ):
        return _NOT_A_PHASE_EVENT
    event = frame[2]
    if event.get("eventType") == "Delete":
        return None
    data = event.get("data")
    return data if isinstance(data, str) or data is None else _NOT_A_PHASE_EVENT


# Talking to the client.


def find_credentials() -> LcuCredentials | None:
    """Find a running client and read its port and token, or None."""
    for proc in psutil.process_iter(["name"]):
        if proc.info["name"] != CLIENT_PROCESS:
            continue
        try:
            credentials = parse_command_line(proc.cmdline())
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        if credentials:
            return credentials
    return None


def _local_tls() -> ssl.SSLContext:
    # The client serves a Riot self-signed certificate on 127.0.0.1 only.
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


class Lcu(Protocol):
    async def get_phase(self) -> str | None: ...

    async def get_game_id(self) -> str | None: ...

    def subscribe_phase(self) -> AsyncIterator[str | None]: ...


class LcuConnection:
    """One client instance, reached through its port and token."""

    def __init__(self, credentials: LcuCredentials, timeout: float = 2.0, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._credentials = credentials
        self._tls = _local_tls()
        self._http = httpx.AsyncClient(
            base_url=f"https://127.0.0.1:{credentials.port}",
            auth=("riot", credentials.token),
            verify=self._tls,
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> "LcuConnection":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    async def get_phase(self) -> str | None:
        try:
            response = await self._http.get(PHASE_PATH)
        except httpx.HTTPError as error:
            raise LcuUnavailable(type(error).__name__) from error
        if response.status_code != 200:
            raise LcuUnavailable(f"HTTP {response.status_code}")
        return parse_phase(response.content)

    async def get_game_id(self) -> str | None:
        try:
            response = await self._http.get("/lol-gameflow/v1/session")
        except httpx.HTTPError as error:
            raise LcuUnavailable(type(error).__name__) from error
        if response.status_code in (404, 204):
            return None
        if response.status_code != 200:
            raise LcuUnavailable(f"HTTP {response.status_code}")
        try:
            value = response.json().get("gameData", {}).get("gameId")
        except (ValueError, AttributeError):
            return None
        value = str(value)
        return value if value.isdigit() and int(value) > 0 else None

    async def subscribe_phase(self) -> AsyncIterator[str | None]:
        basic = base64.b64encode(f"riot:{self._credentials.token}".encode()).decode()
        try:
            async with ws_connect(
                f"wss://127.0.0.1:{self._credentials.port}/",
                additional_headers={"Authorization": f"Basic {basic}"},
                ssl=self._tls,
                open_timeout=5,
            ) as ws:
                await ws.send(json.dumps([_WAMP_SUBSCRIBE, PHASE_EVENT]))
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 1.0)
                    except TimeoutError:
                        # Retry session metadata even when the phase event socket is quiet.
                        yield await self.get_phase()
                        continue
                    phase = parse_phase_event(raw)
                    if phase is not _NOT_A_PHASE_EVENT:
                        yield phase  # type: ignore[misc]
        except (OSError, WebSocketException, TimeoutError) as error:
            raise SubscribeFailed(type(error).__name__) from error
        raise SubscribeFailed("event socket closed")


# Watching.


class GameflowWatcher:
    """Publish every change of the client's state and phase to `on_update`."""

    def __init__(
        self,
        on_update: Callable[[GameflowUpdate], None],
        *,
        discover: Callable[[], LcuCredentials | None] = find_credentials,
        connect: Callable[[LcuCredentials], AbstractAsyncContextManager[Lcu]] = LcuConnection,
        discovery_interval: float = 2.0,
        poll_interval: float = 1.0,
        resubscribe_interval: float = 10.0,
    ) -> None:
        self._on_update = on_update
        self._discover = discover
        self._connect = connect
        self._discovery_interval = discovery_interval
        self._poll_interval = poll_interval
        self._resubscribe_interval = resubscribe_interval
        self._last: GameflowUpdate | None = None

    def _publish(self, update: GameflowUpdate) -> None:
        if update != self._last:
            self._last = update
            self._on_update(update)

    async def run(self) -> None:
        while True:
            credentials = await asyncio.to_thread(self._discover)
            if credentials is None:
                self._publish(NOT_RUNNING)
            else:
                try:
                    async with self._connect(credentials) as lcu:
                        await self._follow(lcu)
                except LcuUnavailable as error:
                    log.info("League client stopped answering (%s)", error)
            await asyncio.sleep(self._discovery_interval)

    async def _publish_phase(self, lcu: Lcu, phase: str | None) -> None:
        # Older phase-only adapters remain usable; production resolves the LCU id.
        get_game_id = getattr(lcu, "get_game_id", None)
        game_id = await get_game_id() if get_game_id and phase in {"InProgress", "Reconnect", "PreEndOfGame", "EndOfGame"} else None
        self._publish(GameflowUpdate(True, phase, game_id))

    async def _follow(self, lcu: Lcu) -> None:
        """Follow one client until it stops answering (raises LcuUnavailable)."""
        await self._publish_phase(lcu, await lcu.get_phase())
        loop = asyncio.get_running_loop()
        while True:
            try:
                async for phase in lcu.subscribe_phase():
                    await self._publish_phase(lcu, phase)
            except SubscribeFailed as error:
                log.info("Gameflow events unavailable (%s); polling", error)
            # Poll until the next subscribe attempt; get_phase raises when the client is gone.
            deadline = loop.time() + self._resubscribe_interval
            while True:
                await self._publish_phase(lcu, await lcu.get_phase())
                if loop.time() >= deadline:
                    break
                await asyncio.sleep(self._poll_interval)
