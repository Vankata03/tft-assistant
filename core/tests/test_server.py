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
            assert await _recv(ws) == {"v": 1, "type": "session_mode", "mode": "silent"}

            server.publish_gameflow(GameflowUpdate(True, "InProgress"))
            assert (await _recv(ws))["phase"] == "InProgress"

            await ws.send(dump(SetSessionMode(mode=SessionMode.LIVE)))
            assert await _recv(ws) == {"v": 1, "type": "session_mode", "mode": "live"}
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
