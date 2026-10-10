"""The localhost WebSocket between the core and the shell.

The shell connects to 127.0.0.1 and sends a Hello with the per-launch token it
gave the core in `TFT_CORE_TOKEN`. Connections that carry an Origin header (any
web page in a browser) are refused, and so are connections that do not say
Hello with the right token within five seconds.
"""

import asyncio
import hmac
import logging
from collections.abc import Callable

from pydantic import ValidationError
from tft_capture.lcu import NOT_RUNNING, GameflowUpdate
from tft_data import DataError
from websockets.asyncio.server import ServerConnection, broadcast, serve
from websockets.exceptions import ConnectionClosed

from tft_core.baseline import BaselineController
from tft_core.baseline.contracts import BaselineState
from tft_core.messages import (
    ErrorMessage,
    Gameflow,
    Hello,
    RequestBaselineState,
    SelectGuide,
    SessionMode,
    SessionModeState,
    SetSessionMode,
    SurfaceShown,
    UnsupportedVersion,
    dump,
    parse_ui_message,
)
from tft_core.storage import SessionStore

log = logging.getLogger(__name__)

HELLO_TIMEOUT = 5.0
POLICY_VIOLATION = 1008


class CoreServer:
    def __init__(
        self,
        token: str,
        *,
        sessions: SessionStore | None = None,
        game_metadata: Callable[[str], dict] | None = None,
        baseline: BaselineController | None = None,
    ) -> None:
        self._token = token
        self._clients: set[ServerConnection] = set()
        self._gameflow = NOT_RUNNING
        self.baseline = baseline or BaselineController()
        self._baseline_clients: set[ServerConnection] = set()
        self.sessions = sessions
        self._game_metadata = game_metadata or (lambda game_id: {})
        self._mode = sessions.mode if sessions else SessionMode.SILENT

    @property
    def mode(self) -> SessionMode:
        return self._mode

    def listen(self, host: str = "127.0.0.1", port: int = 0) -> serve:
        # origins=[None] admits only clients that send no Origin header.
        return serve(self._handle, host, port, origins=[None])

    def publish_gameflow(self, update: GameflowUpdate) -> None:
        self._gameflow = update
        if self.sessions:
            try:
                if update.phase in {"InProgress", "Reconnect"}:
                    if update.game_id:
                        metadata = {}
                        if (
                            self.sessions.active_game_id != update.game_id
                            and not self.sessions.read_events(update.game_id)
                        ):
                            metadata = self._game_metadata(update.game_id)
                        self.sessions.start_game(update.game_id, **metadata)
                    else:
                        broadcast(
                            self._clients,
                            dump(
                                ErrorMessage(
                                    code="missing_game_id",
                                    message="LCU has not supplied a game id; capture cannot log this game yet",
                                )
                            ),
                        )
                elif update.phase in {"EndOfGame", "WaitingForStats"}:
                    self.sessions.end_game()
                elif update.phase in {"Lobby", "None"} and self.sessions.active_game_id:
                    self.sessions.append_event(
                        "capture_gap", {"reason": "game_ended_without_stats"}
                    )
                    self.sessions.end_game()
            except Exception as error:  # noqa: BLE001 -- Storage/metadata failures must leave the connection usable.
                log.error("Session logging failed: %s", error)
                broadcast(
                    self._clients,
                    dump(
                        ErrorMessage(
                            code="session_storage_error",
                            message=f"Game logging is blocked: {error}",
                        )
                    ),
                )
            if self._mode != self.sessions.mode:
                self._mode = self.sessions.mode
                broadcast(self._clients, dump(self._mode_message()))
                self._publish_baseline_state()
        log.info(
            "Gameflow: client_running=%s phase=%s", update.client_running, update.phase
        )
        broadcast(self._clients, dump(self._gameflow_message()))

    def publish_baseline(
        self,
        *,
        data=None,
        snapshot=None,
        faced=(),
        status="Capture OK",
        round_start=False,
        anchors=(),
        overlay_bounds=None,
        overlay_allowed=False,
    ) -> None:
        """Publish pinned data and permitted own capture fields; runtime wiring owns cadence."""
        try:
            self.baseline.update(
                data=data,
                snapshot=snapshot,
                faced=faced,
                status=status,
                round_start=round_start,
                anchors=anchors,
                overlay_bounds=overlay_bounds,
                overlay_allowed=overlay_allowed,
            )
        except DataError, ValidationError, KeyError, TypeError, ValueError:
            self.baseline.update(
                data=None,
                status="Capture status unavailable; invalid capture or calibrated surface fields",
            )
        self._publish_baseline_state()

    def _baseline_state(self) -> BaselineState:
        try:
            return self.baseline.state(self._mode)
        except (DataError, KeyError, TypeError, ValueError) as error:
            return BaselineState(
                mode=self._mode.value, status=f"Baseline data unavailable: {error}"
            )

    def _publish_baseline_state(self) -> None:
        if self._baseline_clients:
            broadcast(self._baseline_clients, dump(self._baseline_state()))

    def _mode_message(self) -> SessionModeState:
        available = (
            tuple(SessionMode)
            if not self.sessions or self.sessions.live_installed
            else (SessionMode.SILENT, SessionMode.BASELINE)
        )
        return SessionModeState(mode=self._mode, available_modes=available)

    def _gameflow_message(self) -> Gameflow:
        return Gameflow(
            client_running=self._gameflow.client_running, phase=self._gameflow.phase
        )

    async def _handle(self, ws: ServerConnection) -> None:
        if not await self._authenticate(ws):
            return
        self._clients.add(ws)
        try:
            await ws.send(dump(self._gameflow_message()))
            await ws.send(dump(self._mode_message()))
            async for raw in ws:
                await self._receive(ws, raw)
        except ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            self._baseline_clients.discard(ws)

    async def _authenticate(self, ws: ServerConnection) -> bool:
        try:
            raw = await asyncio.wait_for(ws.recv(), HELLO_TIMEOUT)
            message = parse_ui_message(raw)
        except TimeoutError, ConnectionClosed, ValueError, ValidationError:
            message = None
        if isinstance(message, Hello) and hmac.compare_digest(
            message.token, self._token
        ):
            return True
        log.warning("Refused a WebSocket client without a valid hello")
        await ws.close(POLICY_VIOLATION, "hello required")
        return False

    async def _receive(self, ws: ServerConnection, raw: str | bytes) -> None:
        try:
            message = parse_ui_message(raw)
        except UnsupportedVersion as error:
            await ws.send(
                dump(ErrorMessage(code="unsupported_version", message=str(error)))
            )
            return
        except (ValueError, ValidationError) as error:
            await ws.send(
                dump(ErrorMessage(code="invalid_message", message=str(error)))
            )
            return
        if isinstance(message, RequestBaselineState):
            self._baseline_clients.add(ws)
            await ws.send(dump(self._baseline_state()))
            return
        if isinstance(message, SelectGuide):
            if self._mode is not SessionMode.BASELINE:
                await ws.send(
                    dump(
                        ErrorMessage(
                            code="baseline_request_rejected",
                            message="Guide selection is available in Baseline mode only",
                        )
                    )
                )
                return
            try:
                self.baseline.select(message.guide_id)
            except DataError as error:
                await ws.send(
                    dump(ErrorMessage(code="guide_unavailable", message=str(error)))
                )
                return
            self._baseline_clients.add(ws)
            if self.sessions and self.sessions.active_game_id:
                self.sessions.append_event(
                    "guide_selection", {"guide_id": message.guide_id}
                )
            self._publish_baseline_state()
            return
        if isinstance(message, SurfaceShown):
            if self._mode is SessionMode.SILENT:
                await ws.send(
                    dump(
                        ErrorMessage(
                            code="surface_suppressed",
                            message="Silent mode suppresses all game content and voice",
                        )
                    )
                )
                return
            if self.sessions and self.sessions.active_game_id:
                self.sessions.append_event(
                    "ui_show",
                    {
                        "surface": message.surface,
                        "content_id": message.content_id,
                        "mode": self._mode.value,
                    },
                    timestamp=message.timestamp.isoformat(),
                )
            return
        if isinstance(message, SetSessionMode):
            ranks = {
                SessionMode.SILENT: 0,
                SessionMode.BASELINE: 1,
                SessionMode.LIVE: 2,
            }
            if (
                self._gameflow.phase in {"InProgress", "Reconnect", "PreEndOfGame"}
                and ranks[message.mode] > ranks[self._mode]
            ):
                await ws.send(
                    dump(
                        ErrorMessage(
                            code="mode_rejected",
                            message="A game can only move to a lower session mode",
                        )
                    )
                )
                return
            if self.sessions:
                try:
                    self.sessions.set_mode(message.mode)
                except ValueError as error:
                    await ws.send(
                        dump(ErrorMessage(code="mode_rejected", message=str(error)))
                    )
                    return
            self._mode = message.mode
            log.info("Session mode: %s", self._mode)
            broadcast(self._clients, dump(self._mode_message()))
            self._publish_baseline_state()
