import asyncio
import json
from contextlib import asynccontextmanager

import pytest

from tft_capture.lcu import (
    NOT_RUNNING,
    PHASE_EVENT,
    GameflowUpdate,
    GameflowWatcher,
    LcuCredentials,
    LcuUnavailable,
    SubscribeFailed,
    _NOT_A_PHASE_EVENT,
    parse_command_line,
    parse_phase,
    parse_phase_event,
)

CLIENT_ARGS = [
    r"C:\Riot Games\League of Legends\LeagueClientUx.exe",
    "--riotclient-auth-token=other",
    "--riotclient-app-port=50000",
    "--remoting-auth-token=s3cret-Token_x",
    "--app-port=61234",
    "--install-directory=C:\\Riot Games\\League of Legends",
]


class TestParseCommandLine:
    def test_reads_port_and_token(self):
        assert parse_command_line(CLIENT_ARGS) == LcuCredentials(61234, "s3cret-Token_x")

    def test_ignores_riot_client_values(self):
        credentials = parse_command_line(CLIENT_ARGS)
        assert credentials is not None
        assert credentials.port != 50000

    def test_strips_quotes(self):
        args = ['"--app-port=61234"', '--remoting-auth-token="abc"']
        assert parse_command_line(args) == LcuCredentials(61234, "abc")

    @pytest.mark.parametrize(
        "args",
        [
            [],
            ["--app-port=61234"],
            ["--remoting-auth-token=abc"],
            ["--app-port=", "--remoting-auth-token=abc"],
            ["--app-port=port", "--remoting-auth-token=abc"],
        ],
    )
    def test_incomplete_arguments_give_none(self, args):
        assert parse_command_line(args) is None

    def test_repr_hides_token(self):
        assert "s3cret" not in repr(parse_command_line(CLIENT_ARGS))


class TestParsePhase:
    @pytest.mark.parametrize("phase", ["None", "Lobby", "InProgress", "Reconnect", "PreEndOfGame"])
    def test_json_string(self, phase):
        assert parse_phase(json.dumps(phase).encode()) == phase

    def test_null(self):
        assert parse_phase(b"null") is None

    @pytest.mark.parametrize("body", [b"{}", b"42", b"not json"])
    def test_rejects_other_bodies(self, body):
        with pytest.raises(ValueError):
            parse_phase(body)


def _event(data, event_type="Update", name=PHASE_EVENT):
    return json.dumps(
        [8, name, {"data": data, "eventType": event_type, "uri": "/lol-gameflow/v1/gameflow-phase"}]
    )


class TestParsePhaseEvent:
    def test_update(self):
        assert parse_phase_event(_event("ChampSelect")) == "ChampSelect"

    def test_delete_gives_none(self):
        assert parse_phase_event(_event(None, "Delete")) is None

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "not json",
            json.dumps([0, "session", 1, "server"]),
            _event("Lobby", name="OnJsonApiEvent_lol-lobby_v2_lobby"),
            _event({"phase": "Lobby"}),
        ],
    )
    def test_other_frames(self, raw):
        assert parse_phase_event(raw) is _NOT_A_PHASE_EVENT


class FakeLcu:
    """A client whose phases and event stream are scripted per test."""

    def __init__(self, polls, events=None):
        self.polls = list(polls)  # values or exceptions returned by get_phase
        self.events = events  # list of phases, or None when subscribing fails

    async def get_phase(self):
        await asyncio.sleep(0)
        value = self.polls.pop(0) if self.polls else LcuUnavailable("gone")
        if isinstance(value, Exception):
            raise value
        return value

    async def subscribe_phase(self):
        if self.events is None:
            raise SubscribeFailed("refused")
        for phase in self.events:
            await asyncio.sleep(0)
            yield phase
        self.events = None
        raise SubscribeFailed("closed")


async def _watch(discoveries, clients, *, expected):
    """Run a watcher over scripted discoveries until `expected` updates arrive."""
    updates = []
    done = asyncio.Event()
    discoveries = list(discoveries)
    clients = list(clients)

    def on_update(update):
        updates.append(update)
        if len(updates) == expected:
            done.set()

    @asynccontextmanager
    async def connect(credentials):
        yield clients.pop(0)

    watcher = GameflowWatcher(
        on_update,
        discover=lambda: discoveries.pop(0) if discoveries else None,
        connect=connect,
        discovery_interval=0,
        poll_interval=0,
        resubscribe_interval=0,
    )
    task = asyncio.create_task(watcher.run())
    await asyncio.wait_for(done.wait(), 2)
    task.cancel()
    return updates


CREDENTIALS = LcuCredentials(1, "t")


def test_watcher_reports_client_not_running():
    updates = asyncio.run(_watch([None, None], [], expected=1))
    assert updates == [NOT_RUNNING]


def test_watcher_follows_events_and_skips_repeats():
    lcu = FakeLcu(polls=["Lobby"], events=["Lobby", "Matchmaking", "ReadyCheck", "ChampSelect", "InProgress"])
    updates = asyncio.run(_watch([CREDENTIALS], [lcu], expected=5))
    assert [u.phase for u in updates] == ["Lobby", "Matchmaking", "ReadyCheck", "ChampSelect", "InProgress"]
    assert all(u.client_running for u in updates)


def test_watcher_polls_when_subscribe_fails():
    lcu = FakeLcu(polls=["Lobby", "Lobby", "InProgress"], events=None)
    updates = asyncio.run(_watch([CREDENTIALS], [lcu], expected=2))
    assert updates == [GameflowUpdate(True, "Lobby"), GameflowUpdate(True, "InProgress")]


def test_watcher_rediscovers_after_client_exits():
    first = FakeLcu(polls=["InProgress", LcuUnavailable("gone")], events=None)
    second = FakeLcu(polls=["Reconnect"], events=["InProgress"])
    updates = asyncio.run(_watch([CREDENTIALS, None, CREDENTIALS], [first, second], expected=5))
    assert updates == [
        GameflowUpdate(True, "InProgress"),
        GameflowUpdate(True, None),
        NOT_RUNNING,
        GameflowUpdate(True, "Reconnect"),
        GameflowUpdate(True, "InProgress"),
    ]


def test_watcher_carries_client_game_id_for_crash_reattachment():
    class Client(FakeLcu):
        async def get_game_id(self):
            return "123456"

    lcu = Client(polls=["InProgress"], events=["Reconnect"])
    updates = asyncio.run(_watch([CREDENTIALS], [lcu], expected=2))
    assert [update.game_id for update in updates] == ["123456", "123456"]


def test_lcu_reads_game_id_from_client_session_response():
    import httpx
    from tft_capture.lcu import LcuConnection

    async def test():
        def client_response(request):
            if request.url.path == "/lol-gameflow/v1/session":
                return httpx.Response(200, json={"gameData": {"gameId": 123456}})
            return httpx.Response(200, json="InProgress")

        async with LcuConnection(CREDENTIALS, transport=httpx.MockTransport(client_response)) as client:
            assert await client.get_phase() == "InProgress"
            assert await client.get_game_id() == "123456"

    asyncio.run(test())
