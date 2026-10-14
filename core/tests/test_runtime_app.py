"""The actual core app: Engine publication, guards and review jobs over public seams.

Only external boundaries are recorded: the League client, window/OCR devices and
patch source files. Storage, capture, Engine, delivery and review run for real.
"""

import asyncio
import contextlib
import io
import json
import pytest
from contextlib import asynccontextmanager

from websockets.asyncio.client import connect

from tests.test_runtime import Devices, fixture_runtime
from tft_capture.lcu import LcuCredentials, LcuUnavailable, SubscribeFailed
from tft_core.messages import Hello, dump


class ScriptedClient:
    """External League client whose phase and game identity the test controls."""

    def __init__(self):
        self.phase, self.game_id, self.mode = "Lobby", None, None
        self.running = True

    async def get_phase(self):
        await asyncio.sleep(0)
        if not self.running:
            raise LcuUnavailable("recorded client exit")
        return self.phase

    async def get_game_identity(self):
        return self.game_id, self.mode

    async def subscribe_phase(self):
        raise SubscribeFailed("recorded polling client")
        yield  # pragma: no cover


@contextlib.asynccontextmanager
async def core(tmp_path, client, *, live_installed=True, devices=None, **options):
    from tft_core.app import run

    _, sessions, data, _ = fixture_runtime(tmp_path)
    sessions.live_installed = live_installed
    closed = asyncio.Event()

    @asynccontextmanager
    async def connect_client(credentials):
        yield client

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        task = asyncio.create_task(
            run(
                "fixture-token",
                sessions=sessions,
                data_store=data,
                settings_path=options.pop("settings_path", tmp_path / "settings.toml"),
                closed=closed,
                devices=devices or Devices(),
                watcher_options={
                    "discover": lambda: LcuCredentials(1, "client-secret"),
                    "connect": connect_client,
                    "discovery_interval": 0.01,
                    "poll_interval": 0.01,
                    "resubscribe_interval": 0.05,
                },
                **options,
            )
        )
        try:
            for _ in range(300):
                if output.getvalue() or task.done():
                    break
                await asyncio.sleep(0.01)
            port = json.loads(output.getvalue().splitlines()[0])["port"]
            async with connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(dump(Hello(token="fixture-token")))
                yield ws, sessions, data, task
        finally:
            closed.set()
            await asyncio.wait_for(task, 15)


async def receive_until(ws, predicate, *, seconds=5):
    seen = []
    try:
        async with asyncio.timeout(seconds):
            while True:
                message = json.loads(await ws.recv())
                seen.append(message)
                if predicate(message):
                    return message, seen
    except TimeoutError as error:
        observed = [
            (m["type"], m.get("mode"), m.get("status"), m.get("message"))
            for m in seen[-32:]
        ]
        raise AssertionError(
            f"Expected public message did not arrive; observed {observed}"
        ) from error


def test_actual_app_publishes_source_gated_live_state_and_enforces_downgrade(tmp_path):
    async def scenario():
        client = ScriptedClient()
        async with core(tmp_path, client) as (ws, sessions, data, task):
            await receive_until(
                ws, lambda m: m["type"] == "gameflow" and m["phase"] == "Lobby"
            )
            await ws.send(
                json.dumps({"v": 1, "type": "set_session_mode", "mode": "live"})
            )
            await receive_until(
                ws, lambda m: m["type"] == "session_mode" and m["mode"] == "live"
            )
            client.phase, client.game_id, client.mode = "InProgress", "123", "TFT"
            await ws.send(json.dumps({"v": 1, "type": "request_live_state"}))
            message, _ = await receive_until(
                ws, lambda m: m["type"] == "live_state" and m.get("content"), seconds=8
            )
            content = message["content"]
            assert message["mode"] == "live"
            assert content["game_id"] == "123"
            assert (
                content["data_snapshot_id"]
                == next(
                    event["payload"]
                    for event in sessions.read_events("123")
                    if event["kind"] == "game_start"
                )["data_snapshot_id"]
            )
            assert content["phase"] == "unknown"
            # This capture fixture supplies no Guides, board or inventory. The
            # real Engine must preserve that source boundary rather than invent
            # useful recommendations merely because Live mode is selected.
            assert content["advice"]
            assert all(row["payload"]["paused"] for row in content["advice"])
            assert any(
                row["payload"]["reason"] == "No validated Guides available"
                for row in content["advice"]
            )
            delivered = [
                event
                for event in sessions.read_events("123")
                if event["kind"] == "advice_delivery"
            ]
            assert any(
                event["payload"]["snapshot_id"] == content["snapshot_id"]
                for event in delivered
            )
            await ws.send(
                json.dumps({"v": 1, "type": "set_session_mode", "mode": "silent"})
            )
            await receive_until(
                ws, lambda m: m["type"] == "session_mode" and m["mode"] == "silent"
            )
            await ws.send(json.dumps({"v": 1, "type": "request_live_state"}))
            silent, _ = await receive_until(
                ws, lambda m: m["type"] == "live_state" and m["mode"] == "silent"
            )
            assert silent["content"] is None
            await ws.send(
                json.dumps({"v": 1, "type": "set_session_mode", "mode": "live"})
            )
            rejected, _ = await receive_until(ws, lambda m: m["type"] == "error")
            assert rejected["code"] == "mode_rejected"
            assert sessions.mode.value == "silent"

    asyncio.run(scenario())


def test_actual_app_finalizes_then_runs_review_child_and_serves_authenticated_report(
    tmp_path,
):
    async def scenario():
        client = ScriptedClient()
        async with core(tmp_path, client) as (ws, sessions, data, task):
            await receive_until(
                ws, lambda m: m["type"] == "gameflow" and m["phase"] == "Lobby"
            )
            await ws.send(
                json.dumps({"v": 1, "type": "set_session_mode", "mode": "live"})
            )
            await receive_until(
                ws, lambda m: m["type"] == "session_mode" and m["mode"] == "live"
            )
            client.phase, client.game_id, client.mode = "InProgress", "123", "TFT"
            await ws.send(json.dumps({"v": 1, "type": "request_live_state"}))
            await receive_until(
                ws, lambda m: m["type"] == "live_state" and m.get("content"), seconds=8
            )
            client.phase = "EndOfGame"
            ready, _ = await receive_until(
                ws, lambda m: m["type"] == "review_ready", seconds=20
            )
            game = next(row for row in sessions.list_games() if row["game_id"] == "123")
            assert game["finished"] is True
            assert game["placement"] is None
            assert ready["game_id"] == "123"
            assert ready["mode"] == "live"
            assert ready["report_id"] == ready["evidence_id"]
            assert ready["latency_seconds"] >= 0
            await ws.send(
                json.dumps(
                    {
                        "v": 1,
                        "type": "request_review",
                        "request_id": "finished-report",
                        "game_id": "123",
                        "operation": "summary",
                        "report_id": ready["report_id"],
                        "evidence_id": ready["evidence_id"],
                    }
                )
            )
            response, _ = await receive_until(
                ws, lambda m: m.get("request_id") == "finished-report"
            )
            assert response["type"] == "review_response"
            assert response["value"]["locked"] is False
            assert response["value"]["report_id"] == ready["report_id"]

    asyncio.run(scenario())


@pytest.mark.parametrize("live_installed", [True, False])
def test_actual_app_keeps_modes_guarded_when_positive_game_has_no_capture_settings(
    tmp_path, live_installed
):
    async def scenario():
        client, devices = ScriptedClient(), Devices()
        missing = tmp_path / "absent.toml"
        async with core(
            tmp_path,
            client,
            devices=devices,
            settings_path=missing,
            live_installed=live_installed,
        ) as (ws, sessions, data, task):
            await receive_until(
                ws, lambda m: m["type"] == "gameflow" and m["phase"] == "Lobby"
            )
            await ws.send(
                json.dumps({"v": 1, "type": "set_session_mode", "mode": "baseline"})
            )
            modes, _ = await receive_until(
                ws, lambda m: m["type"] == "session_mode" and m["mode"] == "baseline"
            )
            if not live_installed:
                assert set(modes["available_modes"]) == {"silent", "baseline"}
            original_data = data.current.snapshot_id
            client.phase, client.game_id, client.mode = "InProgress", "123", "TFT"
            await receive_until(
                ws, lambda m: m["type"] == "gameflow" and m["phase"] == "InProgress"
            )
            await ws.send(json.dumps({"v": 1, "type": "request_baseline_state"}))
            unavailable, _ = await receive_until(
                ws,
                lambda m: m["type"] == "baseline_state" and str(missing) in m["status"],
            )
            assert unavailable["content"] is None
            assert devices.opens == 0
            assert sessions.read_events("123") == []
            assert data.current.snapshot_id == original_data
            await ws.send(
                json.dumps({"v": 1, "type": "set_session_mode", "mode": "live"})
            )
            rejected, _ = await receive_until(ws, lambda m: m["type"] == "error")
            assert rejected["code"] == "mode_rejected"
            await ws.send(
                json.dumps({"v": 1, "type": "set_session_mode", "mode": "silent"})
            )
            await receive_until(
                ws, lambda m: m["type"] == "session_mode" and m["mode"] == "silent"
            )
            await ws.send(json.dumps({"v": 1, "type": "request_live_state"}))
            silent, _ = await receive_until(
                ws, lambda m: m["type"] == "live_state" and m["mode"] == "silent"
            )
            assert silent["content"] is None

    asyncio.run(scenario())
