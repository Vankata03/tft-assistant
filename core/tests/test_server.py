import asyncio
import json

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from tft_capture.lcu import GameflowUpdate
from tft_core.messages import Hello, SessionMode, SetSessionMode, dump
from tft_core.server import CoreServer

TOKEN = "launch-token"


async def _with_server(test):
    server = CoreServer(TOKEN)
    async with server.listen() as ws_server:
        port = ws_server.sockets[0].getsockname()[1]
        await test(server, f"ws://127.0.0.1:{port}")


async def _recv(ws):
    return json.loads(await asyncio.wait_for(ws.recv(), 2))


def test_hello_gets_current_state_and_mode_changes_broadcast():
    async def test(server, url):
        async with connect(url) as ws:
            await ws.send(dump(Hello(token=TOKEN)))
            assert await _recv(ws) == {"v": 1, "type": "gameflow", "client_running": False, "phase": None}
            assert await _recv(ws) == {"v": 1, "type": "session_mode", "mode": "silent", "available_modes": ["silent", "baseline", "live"]}

            server.publish_gameflow(GameflowUpdate(True, "InProgress"))
            assert (await _recv(ws))["phase"] == "InProgress"

            await ws.send(dump(SetSessionMode(mode=SessionMode.LIVE)))
            assert await _recv(ws) == {"v": 1, "type": "session_mode", "mode": "live", "available_modes": ["silent", "baseline", "live"]}
            assert server.mode is SessionMode.LIVE

    asyncio.run(_with_server(test))


def test_wrong_token_is_closed():
    async def test(server, url):
        async with connect(url) as ws:
            await ws.send(dump(Hello(token="wrong")))
            with pytest.raises(ConnectionClosed) as closed:
                await ws.recv()
            assert closed.value.rcvd.code == 1008

    asyncio.run(_with_server(test))


def test_browser_origin_is_refused():
    async def test(server, url):
        with pytest.raises(InvalidStatus):
            async with connect(url, origin="https://example.com"):
                pass

    asyncio.run(_with_server(test))


def test_invalid_message_gets_error():
    async def test(server, url):
        async with connect(url) as ws:
            await ws.send(dump(Hello(token=TOKEN)))
            await _recv(ws)
            await _recv(ws)
            await ws.send('{"v": 1, "type": "set_session_mode", "mode": "turbo"}')
            assert (await _recv(ws))["code"] == "invalid_message"
            await ws.send('{"v": 9, "type": "set_session_mode", "mode": "live"}')
            assert (await _recv(ws))["code"] == "unsupported_version"
            assert server.mode is SessionMode.SILENT

    asyncio.run(_with_server(test))


def test_durable_session_enforces_downgrades_and_logs_modes(tmp_path):
    from tft_core.storage import SessionStore

    async def test():
        storage = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
        storage.set_mode(SessionMode.LIVE)
        server = CoreServer(TOKEN, sessions=storage)
        async with server.listen() as listening:
            url = f"ws://127.0.0.1:{listening.sockets[0].getsockname()[1]}"
            async with connect(url) as ws:
                await ws.send(dump(Hello(token=TOKEN)))
                await _recv(ws)
                assert (await _recv(ws))["mode"] == "live"
                server.publish_gameflow(GameflowUpdate(True, "InProgress", "991"))
                await _recv(ws)
                await ws.send(dump(SetSessionMode(mode=SessionMode.SILENT)))
                assert (await _recv(ws))["mode"] == "silent"
                await ws.send(dump(SetSessionMode(mode=SessionMode.LIVE)))
                assert (await _recv(ws))["code"] == "mode_rejected"
                server.publish_gameflow(GameflowUpdate(True, "EndOfGame", "991"))
                assert storage.list_games()[0]["mode"] == "live"
                assert [e["kind"] for e in storage.read_events("991")] == ["game_start", "mode_change", "game_end"]

    asyncio.run(test())


def test_public_build_advertises_only_silent_and_baseline(tmp_path):
    from tft_core.storage import SessionStore

    async def test():
        session = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=False)
        server = CoreServer(TOKEN, sessions=session)
        async with server.listen() as listening:
            async with connect(f"ws://127.0.0.1:{listening.sockets[0].getsockname()[1]}") as ws:
                await ws.send(dump(Hello(token=TOKEN)))
                await _recv(ws)
                state = await _recv(ws)
                assert state["available_modes"] == ["silent", "baseline"]
                assert state["mode"] == "baseline"

    asyncio.run(test())


def test_session_start_pins_supplied_data_and_model_metadata(tmp_path):
    from tft_core.storage import SessionStore

    session = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    server = CoreServer(TOKEN, sessions=session, game_metadata=lambda game_id: {
        "patch": "18.3", "data_snapshot_id": "immutable-a", "model_version": "reader-a", "set_id": "18", "engine_version": "abc+dirty", "previous_patch": True,
    })
    server.publish_gameflow(GameflowUpdate(True, "InProgress", "900"))
    header = session.read_events("900")[0]["payload"]
    assert header["data_snapshot_id"] == "immutable-a"
    assert header["model_version"] == "reader-a"
    assert header["previous_patch"] is True
