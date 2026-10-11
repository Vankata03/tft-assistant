"""Supervised runtime through real storage/capture and external device fixtures."""

import asyncio
import json
import threading
import runpy
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from PIL import Image

from tft_capture.lcu import GameflowUpdate, LcuConnection, LcuCredentials
from tft_capture.ocr import TextLine
from tft_capture.windows import CapturedFrame
from tft_core.server import CoreServer
from tft_core.storage import SessionStore
from tft_data import DataStore
patch_files = runpy.run_path(str(Path(__file__).parents[1] / "packages/data/tests/test_refresh.py"))["patch_files"]


@pytest.mark.parametrize("game_data,expected", [
    ({"gameId": 123, "queue": {"gameMode": "TFT"}}, "TFT"),
    ({"gameId": 123, "gameMode": "CLASSIC"}, "CLASSIC"),
    ({"gameId": 123, "queue": {"id": 1100}}, None),
    ({"gameId": 123, "gameMode": "CLASSIC", "queue": {"gameMode": "TFT"}}, None),
])
def test_lcu_identity_requires_an_explicit_consistent_mode(game_data, expected):
    async def scenario():
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"gameData": game_data}))
        async with LcuConnection(LcuCredentials(1, "fixture-token"), transport=transport) as lcu:
            identity = await lcu.get_game_identity()
            assert identity == ("123", expected)
    asyncio.run(scenario())


class Devices:
    """Recorded external OCR and window boundary, never application collaborators."""
    source = "recorded-runtime-ocr"

    def __init__(self, *, failure=False):
        self.opens = 0
        self.failure = failure
        self.closed = threading.Event()

    def open(self, settings, data):
        self.opens += 1
        return self, self, None

    def capture(self):
        if self.failure:
            raise RuntimeError("Recorded driver failed")
        return CapturedFrame(Image.new("RGB", (100, 100), "white"), "window-a", "recorded")

    def read(self, image, *, region):
        text = {"stage": "2-1", "players": "Owner", "gold": "28", "level": "4"}.get(region)
        return [TextLine(text, 1)] if text else []

    def close(self):
        self.closed.set()


def fixture_runtime(tmp_path, *, devices=None):
    from tft_core.runtime import CaptureRuntime, RuntimeSettings
    patch = patch_files(tmp_path / "patch")
    data = DataStore(tmp_path / "snapshots")
    snapshot = data.refresh(patch).snapshot
    (tmp_path / "profile.json").write_text(json.dumps({"version": 1, "regions": {
        "stage": [0, 0, 1, 1], "players": [0, 0, 1, 1], "gold": [0, 0, 1, 1], "level": [0, 0, 1, 1]}}))
    (tmp_path / "game.cfg").write_text("[HUD]\nGlobalScale=1\n[General]\nWindowMode=2\n")
    (tmp_path / "models.json").write_text(json.dumps({"version": "fixture-reader"}))
    (tmp_path / "names.json").write_text(json.dumps({"snapshot_id": snapshot.snapshot_id,
        "locale": "en_us", "names": {"units": {"fixture-unit": "Fixture unit"}}}))
    settings_path = tmp_path / "settings.toml"
    settings_path.write_text('schema_version=1\nowner_name="Owner"\nlocale="en_us"\nexpected_patch="test.1"\n'
        'profile="profile.json"\ngame_config="game.cfg"\nmodels="models"\nmodel_pointer="models.json"\n'
        'names="names.json"\npatch_dir="patch"\n')
    sessions = SessionStore(tmp_path / "logs", tmp_path / "config", live_installed=False)
    server = CoreServer("token", sessions=sessions, managed_lifecycle=True)
    runtime = CaptureRuntime(server, sessions, data, settings=RuntimeSettings.load(settings_path), devices=devices or Devices())
    return runtime, sessions, data, server


async def wait_snapshot(runtime):
    for _ in range(200):
        if runtime.latest_snapshot is not None:
            return runtime.latest_snapshot
        await asyncio.sleep(.01)
    raise AssertionError("Capture did not publish a snapshot")


def test_runtime_one_worker_original_pins_and_unknown_shutdown(tmp_path):
    async def scenario():
        devices = Devices()
        runtime, sessions, data, server = fixture_runtime(tmp_path, devices=devices)
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        snapshot = await wait_snapshot(runtime)
        assert snapshot["game_id"] == "123"
        header = sessions.read_events("123")[0]["payload"]
        assert header["data_snapshot_id"] == data.current.snapshot_id
        assert header["model_version"] == "fixture-reader"
        await runtime.update(GameflowUpdate(True, "Reconnect", "123", "TFT"))
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        assert devices.opens == 1
        await runtime.shutdown()
        events = sessions.read_events("123")
        assert sum(event["kind"] == "game_start" for event in events) == 1
        assert events[-1]["kind"] == "capture_closed"
        assert not any(event["kind"] == "game_end" for event in events)
        assert sessions.active_game_id == "123"
        assert devices.closed.is_set()
    asyncio.run(scenario())


@pytest.mark.parametrize("mode", [None, "CLASSIC"])
def test_runtime_rejects_unidentified_and_non_tft_games(tmp_path, mode):
    async def scenario():
        runtime, sessions, data, server = fixture_runtime(tmp_path)
        await runtime.update(GameflowUpdate(True, "InProgress", "123", mode))
        assert sessions.active_game_id is None
        assert runtime.latest_snapshot is None
        assert "TFT" in runtime.status
        await runtime.shutdown()
    asyncio.run(scenario())


def test_terminal_flushes_capture_before_end_and_retains_completed_mode(tmp_path):
    async def scenario():
        runtime, sessions, data, server = fixture_runtime(tmp_path)
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        await wait_snapshot(runtime)
        sessions.set_mode("silent")
        await runtime.update(GameflowUpdate(True, "EndOfGame", "123", "TFT"))
        events = sessions.read_events("123")
        kinds = [event["kind"] for event in events]
        assert kinds.index("capture_closed") < kinds.index("game_end")
        assert events[-1]["payload"]["placement"] is None
        assert runtime.completed_game["final_mode"] == "silent"
        assert sessions.active_game_id is None
        await runtime.shutdown()
    asyncio.run(scenario())


def test_client_loss_and_new_process_reattach_use_original_data(tmp_path):
    async def scenario():
        runtime, sessions, data, server = fixture_runtime(tmp_path)
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        await wait_snapshot(runtime)
        pin = data.current
        await runtime.update(GameflowUpdate(False, None))
        assert not any(event["kind"] == "game_end" for event in sessions.read_events("123"))
        await runtime.shutdown()
        from tft_core.runtime import CaptureRuntime
        resumed_store = SessionStore(sessions.root, sessions.config_root, live_installed=False)
        resumed = CaptureRuntime(CoreServer("other", sessions=resumed_store, managed_lifecycle=True),
            resumed_store, DataStore(data.root), settings=runtime.settings, devices=Devices())
        await resumed.update(GameflowUpdate(True, "Reconnect", "123", "TFT"))
        assert (await wait_snapshot(resumed))["data_snapshot_id"] == pin.snapshot_id
        assert any(event["kind"] == "capture_gap" and event["payload"]["reason"] == "core_restart"
            for event in resumed_store.read_events("123"))
        await resumed.shutdown()
    asyncio.run(scenario())


def test_worker_error_remains_visible_and_watcher_can_follow_lobby(tmp_path):
    async def scenario():
        runtime, sessions, data, server = fixture_runtime(tmp_path, devices=Devices(failure=True))
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        for _ in range(100):
            if "driver failed" in runtime.status:
                break
            await asyncio.sleep(.01)
        assert "driver failed" in runtime.status
        assert runtime.latest_snapshot is None
        await runtime.update(GameflowUpdate(True, "Lobby"))
        assert sessions.active_game_id == "123"
        assert not any(event["kind"] == "game_end" for event in sessions.read_events("123"))
        await runtime.shutdown()
    asyncio.run(scenario())


def test_refresh_coalesces_and_cannot_replace_active_pin(tmp_path):
    async def scenario():
        runtime, sessions, data, server = fixture_runtime(tmp_path)
        await runtime.start()
        first = runtime.refresh.task
        await runtime.update(GameflowUpdate(True, "Lobby"))
        assert runtime.refresh.task is first
        await first
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        await wait_snapshot(runtime)
        pin = runtime.pinned_data
        await runtime.update(GameflowUpdate(True, "Lobby"))
        assert runtime.refresh.task is first
        (runtime.settings.patch_dir / "static.toml").unlink()
        await runtime.update(GameflowUpdate(True, "Reconnect", "123", "TFT"))
        await wait_snapshot(runtime)
        await runtime.update(GameflowUpdate(True, "EndOfGame", "123", "TFT"))
        await runtime.refresh.wait()
        assert data.current.snapshot_id == pin.snapshot_id
        assert "unavailable" in runtime.status.lower() or "missing" in runtime.status.lower()
        await runtime.shutdown()
    asyncio.run(scenario())


def test_stalled_native_worker_timeout_keeps_log_unfinished(tmp_path):
    class Stalled(Devices):
        def capture(self):
            self.closed.wait(2)
            return super().capture()

        def close(self):
            pass

    async def scenario():
        devices = Stalled()
        runtime, sessions, data, server = fixture_runtime(tmp_path, devices=devices)
        runtime.shutdown_seconds = .05
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        await asyncio.sleep(.03)
        await runtime.update(GameflowUpdate(True, "EndOfGame", "123", "TFT"))
        assert "timed out" in runtime.status
        assert sessions.active_game_id == "123"
        assert any(event["kind"] == "capture_shutdown_timeout" for event in sessions.read_events("123"))
        assert not any(event["kind"] == "game_end" for event in sessions.read_events("123"))
        devices.closed.set()
        await runtime.shutdown()
    asyncio.run(scenario())


def test_gap_aware_fight_projection_never_certifies_a_later_prefix():
    from tft_core.runtime import project_fight_history
    history = [
        {"kind": "game_start", "timestamp": "2026-10-11T10:00:00+00:00", "payload": {}},
        {"kind": "capture_history_start", "timestamp": "2026-10-11T10:00:01+00:00", "payload": {"round_id": "1-1", "expected_first_round": "1-1"}},
        {"kind": "fight_start", "timestamp": "2026-10-11T10:01:00+00:00", "payload": {"round_id": "2-1", "opponent_id": "Rival"}},
        {"kind": "fight_result", "timestamp": "2026-10-11T10:01:30+00:00", "payload": {"round_id": "2-1", "opponent_id": "Rival", "result": "win"}},
    ]
    assert project_fight_history(history, "2026-10-11T10:01:10+00:00")["recent_opponent_fights_complete"]["value"] is False
    projected = project_fight_history(history, "2026-10-11T10:02:00+00:00")
    assert projected["recent_opponent_fights_complete"]["value"] is True
    row = projected["recent_opponent_fights"]["value"][0]
    assert row["read_at"] == history[2]["timestamp"]
    history.append({"kind": "capture_gap", "timestamp": "2026-10-11T10:02:01+00:00", "payload": {"reason": "core_restart"}})
    assert project_fight_history(history, "2026-10-11T10:03:00+00:00")["recent_opponent_fights_complete"]["value"] is False


def test_game_start_without_observed_initial_capture_does_not_certify_fights():
    from tft_core.runtime import project_fight_history
    history = [{"kind": "game_start", "timestamp": "2026-10-11T10:00:00+00:00", "payload": {}}]
    assert project_fight_history(history, "2026-10-11T10:03:00+00:00")["recent_opponent_fights_complete"]["value"] is False


def test_actual_capture_producer_certifies_checked_start_then_retains_fight_times(tmp_path):
    from tft_capture.vision import VisionRead

    class RecordedFight(Devices):
        def __init__(self):
            super().__init__()
            self.frame = 0

        def open(self, settings, data):
            self.opens += 1
            return self, self, self

        units = None
        identity_min = .55
        model_version = "fixture-reader"
        label_map = {}

        def capture(self):
            self.frame += 1
            return CapturedFrame(Image.new("RGB", (100, 100), (self.frame % 255, 0, 0)), "a", "recorded")

        def read(self, image, *, region=None, regions=None, own_view=None):
            if regions is not None:
                fields = {"phase": "carousel" if self.frame == 1 else "combat", "hp": 100,
                    "fight_opponent": "Rival"}
                if self.frame >= 3:
                    fields["fight_result"] = "win"
                return VisionRead(fields, "recorded-fight", 1)
            if region == "stage":
                return [TextLine("1-1" if self.frame == 1 else "2-1", 1)]
            if region == "scouted":
                return [TextLine("Owner Level 4", 1)]
            return super().read(image, region=region)

    async def scenario():
        devices = RecordedFight()
        runtime, sessions, data, server = fixture_runtime(tmp_path, devices=devices)
        profile = json.loads(runtime.settings.profile.read_text())
        profile["regions"]["board"] = [0, 0, 1, 1]
        profile["regions"]["scouted"] = [0, 0, 1, 1]
        runtime.settings.profile.write_text(json.dumps(profile))
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        for _ in range(10):
            snapshot = await asyncio.wait_for(runtime.next_snapshot(), 2)
            fields = snapshot["fields"]
            if fields["recent_opponent_fights"]["value"]:
                break
        assert fields["recent_opponent_fights_complete"]["value"] is True
        row = fields["recent_opponent_fights"]["value"][0]
        events = sessions.read_events("123")
        start = next(event for event in events if event["kind"] == "fight_start")
        assert row["read_at"] == start["timestamp"]
        assert any(event["kind"] == "capture_history_start" for event in events)
        await runtime.shutdown()
    asyncio.run(scenario())


def test_authenticated_runtime_surfaces_silent_clearing_and_public_modes(tmp_path):
    from websockets.asyncio.client import connect
    from tft_core.messages import Hello, dump

    async def scenario():
        runtime, sessions, data, server = fixture_runtime(tmp_path)
        async with server.listen() as listening:
            async with connect(f"ws://127.0.0.1:{listening.sockets[0].getsockname()[1]}") as ws:
                await ws.send(dump(Hello(token="token")))
                await ws.recv()
                modes = json.loads(await ws.recv())
                assert modes["available_modes"] == ["silent", "baseline"]
                await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
                await wait_snapshot(runtime)
                await ws.send(json.dumps({"v": 1, "type": "request_baseline_state"}))
                while (state := json.loads(await ws.recv()))["type"] != "baseline_state":
                    pass
                assert state["mode"] == "baseline"
                assert state["content"] is not None
                await ws.send(json.dumps({"v": 1, "type": "set_session_mode", "mode": "silent"}))
                while (state := json.loads(await ws.recv()))["type"] != "baseline_state" or state["mode"] != "silent":
                    pass
                assert state["content"] is None and state["voice"] is None
        await runtime.shutdown()
    asyncio.run(scenario())


@pytest.mark.parametrize("with_run", [False, True])
def test_completed_permissions_come_from_stored_game_before_mode_reset(tmp_path, with_run):
    async def scenario():
        runtime, sessions, data, server = fixture_runtime(tmp_path)
        sessions.live_installed = True
        if with_run:
            sessions.start_run({"game_count": 50, "average_placement": 4.2, "rank": "Fixture rank"}, set_id="18")
        sessions.set_mode("silent")
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        await wait_snapshot(runtime)
        await runtime.update(GameflowUpdate(True, "EndOfGame", "123", "TFT"))
        stored = next(game for game in sessions.list_games() if game["game_id"] == "123")
        assert runtime.completed_game["review_locked"] is stored["review_locked"]
        assert runtime.completed_game["mode"] == stored["mode"]
        assert runtime.completed_game["final_mode"] == "silent"
        assert stored["review_locked"] is (not with_run)
        await runtime.shutdown()
    asyncio.run(scenario())


def test_real_process_eof_does_not_wait_for_blocked_external_refresh(tmp_path):
    runtime, sessions, data, server = fixture_runtime(tmp_path)
    entered, release = threading.Event(), threading.Event()

    class Response(BaseHTTPRequestHandler):
        def do_GET(self):
            entered.set()
            release.wait(5)
            body = json.dumps({"patch": "test.1", "updated": int(time.time() * 1000), "rows": []}).encode()
            self.send_response(200)
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Response)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    sources = tmp_path / "sources.toml"
    sources.write_text('schema_version=1\n[statistics]\nminimum_rank="DIAMOND"\nregions="all"\n'
        '[refresh]\nsources=["slow"]\n[sources.slow]\nprovider="metatft"\nkind="statistics"\n'
        'url="https://source-fixture.invalid/rows"\ntimeout=15\n')
    settings_path = tmp_path / "settings.toml"
    settings_path.write_text(settings_path.read_text() + 'sources="sources.toml"\n')
    code = """
import asyncio, sys, urllib.request
from pathlib import Path
from tft_core.app import run
from tft_core.storage import SessionStore
original_urlopen = urllib.request.urlopen
def recorded_service(request, *, timeout):
    assert request.full_url == 'https://source-fixture.invalid/rows'
    return original_urlopen('http://127.0.0.1:' + sys.argv[4] + '/rows', timeout=timeout)
urllib.request.urlopen = recorded_service
asyncio.run(run('fixture-token', sessions=SessionStore(Path(sys.argv[1]),Path(sys.argv[2]),live_installed=False),settings_path=Path(sys.argv[3]),watcher_options={'discover':lambda:None}))
"""
    child = subprocess.Popen([sys.executable, "-c", code, str(sessions.root), str(sessions.config_root), str(settings_path), str(http.server_port)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert json.loads(child.stdout.readline())["event"] == "ready"
        assert entered.wait(3)
        started = time.monotonic()
        child.stdin.close()
        child.wait(timeout=1.5)
        assert child.returncode == 0, child.stderr.read()
        assert time.monotonic() - started < 1.5
        assert "refresh" in child.stderr.read().lower()
    finally:
        release.set()
        if not child.stdin.closed:
            child.stdin.close()
        child.wait(timeout=10)
        http.shutdown()
        http.server_close()
