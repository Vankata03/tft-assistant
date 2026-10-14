"""Supervised runtime through real storage/capture and external device fixtures."""

from tests.test_harness_baseline import baseline_fixture

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

patch_files = runpy.run_path(
    str(Path(__file__).parents[1] / "packages/data/tests/test_refresh.py")
)["patch_files"]


@pytest.mark.parametrize(
    "game_data,expected",
    [
        ({"gameId": 123, "queue": {"gameMode": "TFT"}}, "TFT"),
        ({"gameId": 123, "gameMode": "CLASSIC"}, "CLASSIC"),
        ({"gameId": 123, "queue": {"id": 1100}}, None),
        ({"gameId": 123, "gameMode": "CLASSIC", "queue": {"gameMode": "TFT"}}, None),
    ],
)
def test_lcu_identity_requires_an_explicit_consistent_mode(game_data, expected):
    async def scenario():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"gameData": game_data})
        )
        async with LcuConnection(
            LcuCredentials(1, "fixture-token"), transport=transport
        ) as lcu:
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
        return CapturedFrame(
            Image.new("RGB", (100, 100), "white"), "window-a", "recorded"
        )

    def read(self, image, *, region):
        text = {"stage": "2-1", "players": "Owner", "gold": "28", "level": "4"}.get(
            region
        )
        return [TextLine(text, 1)] if text else []

    def close(self):
        self.closed.set()


def fixture_runtime(tmp_path, *, devices=None):
    from tft_core.runtime import CaptureRuntime, RuntimeSettings

    patch = patch_files(tmp_path / "patch")
    data = DataStore(tmp_path / "snapshots")
    snapshot = data.refresh(patch).snapshot
    (tmp_path / "profile.json").write_text(
        json.dumps(
            {
                "version": 1,
                "regions": {
                    "stage": [0, 0, 1, 1],
                    "players": [0, 0, 1, 1],
                    "gold": [0, 0, 1, 1],
                    "level": [0, 0, 1, 1],
                },
            }
        )
    )
    (tmp_path / "game.cfg").write_text(
        "[HUD]\nGlobalScale=1\n[General]\nWindowMode=2\n"
    )
    (tmp_path / "models.json").write_text(json.dumps({"version": "fixture-reader"}))
    (tmp_path / "names.json").write_text(
        json.dumps(
            {
                "snapshot_id": snapshot.snapshot_id,
                "locale": "en_us",
                "names": {"units": {"fixture-unit": "Fixture unit"}},
            }
        )
    )
    settings_path = tmp_path / "settings.toml"
    settings_path.write_text(
        'schema_version=1\nowner_name="Owner"\nwindow_title="fixture-window"\nlocale="en_us"\nexpected_patch="test.1"\n'
        'profile="profile.json"\ngame_config="game.cfg"\nmodels="models"\nmodel_pointer="models.json"\n'
        'names="names.json"\ndigits="calibrated-glyphs"\npatch_dir="patch"\n'
    )
    sessions = SessionStore(
        tmp_path / "logs", tmp_path / "config", live_installed=False
    )
    server = CoreServer("token", sessions=sessions, managed_lifecycle=True)
    runtime = CaptureRuntime(
        server,
        sessions,
        data,
        settings=RuntimeSettings.load(settings_path),
        devices=devices or Devices(),
    )
    return runtime, sessions, data, server


async def wait_snapshot(runtime):
    for _ in range(200):
        if runtime.latest_snapshot is not None:
            return runtime.latest_snapshot
        await asyncio.sleep(0.01)
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
        assert not any(
            event["kind"] == "game_end" for event in sessions.read_events("123")
        )
        await runtime.shutdown()
        from tft_core.runtime import CaptureRuntime

        resumed_store = SessionStore(
            sessions.root, sessions.config_root, live_installed=False
        )
        resumed = CaptureRuntime(
            CoreServer("other", sessions=resumed_store, managed_lifecycle=True),
            resumed_store,
            DataStore(data.root),
            settings=runtime.settings,
            devices=Devices(),
        )
        await resumed.update(GameflowUpdate(True, "Reconnect", "123", "TFT"))
        assert (await wait_snapshot(resumed))["data_snapshot_id"] == pin.snapshot_id
        assert any(
            event["kind"] == "capture_gap"
            and event["payload"]["reason"] == "core_restart"
            for event in resumed_store.read_events("123")
        )
        await resumed.shutdown()

    asyncio.run(scenario())


def test_worker_error_remains_visible_and_watcher_can_follow_lobby(tmp_path):
    async def scenario():
        runtime, sessions, data, server = fixture_runtime(
            tmp_path, devices=Devices(failure=True)
        )
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        for _ in range(100):
            if "driver failed" in runtime.status:
                break
            await asyncio.sleep(0.01)
        assert "driver failed" in runtime.status
        assert runtime.latest_snapshot is None
        await runtime.update(GameflowUpdate(True, "Lobby"))
        assert sessions.active_game_id == "123"
        assert not any(
            event["kind"] == "game_end" for event in sessions.read_events("123")
        )
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
        lobby_refresh = runtime.refresh.task
        await runtime.update(GameflowUpdate(True, "Lobby"))
        assert runtime.refresh.task is lobby_refresh
        assert runtime.pinned_data is pin
        await runtime.refresh.wait()
        (runtime.settings.patch_dir / "static.toml").unlink()
        await runtime.update(GameflowUpdate(True, "Reconnect", "123", "TFT"))
        await wait_snapshot(runtime)
        await runtime.update(GameflowUpdate(True, "EndOfGame", "123", "TFT"))
        await runtime.refresh.wait()
        assert data.current.snapshot_id == pin.snapshot_id
        assert (
            "unavailable" in runtime.status.lower()
            or "missing" in runtime.status.lower()
        )
        await runtime.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "transition",
    [
        GameflowUpdate(True, "EndOfGame", "123", "TFT"),
        GameflowUpdate(True, "EndOfGame", None, None),
        GameflowUpdate(True, "InProgress", "123", None),
        GameflowUpdate(False, None),
        GameflowUpdate(False, None, error="Watcher unavailable: RuntimeError"),
    ],
)
def test_stalled_native_worker_timeout_keeps_log_unfinished(tmp_path, transition):
    class Stalled(Devices):
        def __init__(self):
            super().__init__()
            self.entered = threading.Event()

        def capture(self):
            self.entered.set()
            self.closed.wait(2)
            return super().capture()

        def close(self):
            pass

    async def scenario():
        devices = Stalled()
        runtime, sessions, data, server = fixture_runtime(tmp_path, devices=devices)
        runtime.shutdown_seconds = 0.05
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        for _ in range(200):
            if devices.entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert devices.entered.is_set()
        await runtime.update(transition)
        assert "timed out" in runtime.status
        assert sessions.active_game_id == "123"
        assert any(
            event["kind"] == "capture_shutdown_timeout"
            for event in sessions.read_events("123")
        )
        assert not any(
            event["kind"] == "game_end" for event in sessions.read_events("123")
        )
        await runtime.update(GameflowUpdate(True, "InProgress", "456", "TFT"))
        assert sessions.active_game_id == "123"
        assert sessions.read_events("456") == []
        devices.closed.set()
        await runtime.shutdown()

    asyncio.run(scenario())


def test_gap_aware_fight_projection_never_certifies_a_later_prefix():
    from tft_core.runtime import project_fight_history

    history = [
        {"kind": "game_start", "timestamp": "2026-10-11T10:00:00+00:00", "payload": {}},
        {
            "kind": "capture_history_start",
            "timestamp": "2026-10-11T10:00:01+00:00",
            "payload": {"round_id": "1-1", "expected_first_round": "1-1"},
        },
        {
            "kind": "fight_start",
            "timestamp": "2026-10-11T10:01:00+00:00",
            "payload": {"round_id": "2-1", "opponent_id": "Rival"},
        },
        {
            "kind": "fight_result",
            "timestamp": "2026-10-11T10:01:30+00:00",
            "payload": {"round_id": "2-1", "opponent_id": "Rival", "result": "win"},
        },
    ]
    assert (
        project_fight_history(
            history,
            "2026-10-11T10:01:10+00:00",
            round_types={"1-1": "carousel", "2-1": "combat"},
        )["recent_opponent_fights_complete"]["value"]
        is False
    )
    projected = project_fight_history(
        history,
        "2026-10-11T10:02:00+00:00",
        round_types={"1-1": "carousel", "2-1": "combat"},
    )
    assert projected["recent_opponent_fights_complete"]["value"] is True
    row = projected["recent_opponent_fights"]["value"][0]
    assert row["read_at"] == history[2]["timestamp"]
    history.append(
        {
            "kind": "capture_gap",
            "timestamp": "2026-10-11T10:02:01+00:00",
            "payload": {"reason": "core_restart"},
        }
    )
    assert (
        project_fight_history(
            history,
            "2026-10-11T10:03:00+00:00",
            round_types={"1-1": "carousel", "2-1": "combat"},
        )["recent_opponent_fights_complete"]["value"]
        is False
    )


def test_game_start_without_observed_initial_capture_does_not_certify_fights():
    from tft_core.runtime import project_fight_history

    history = [
        {"kind": "game_start", "timestamp": "2026-10-11T10:00:00+00:00", "payload": {}}
    ]
    assert (
        project_fight_history(history, "2026-10-11T10:03:00+00:00")[
            "recent_opponent_fights_complete"
        ]["value"]
        is False
    )


def test_actual_capture_producer_certifies_checked_start_then_retains_fight_times(
    tmp_path,
):
    from tft_capture.vision import VisionRead

    class RecordedFight(Devices):
        def __init__(self):
            super().__init__()
            self.frame = 0

        def open(self, settings, data):
            self.opens += 1
            return self, self, self

        units = None
        identity_min = 0.55
        model_version = "fixture-reader"
        label_map = {}

        def capture(self):
            self.frame += 1
            return CapturedFrame(
                Image.new("RGB", (100, 100), (self.frame % 255, 0, 0)), "a", "recorded"
            )

        def read(self, image, *, region=None, regions=None, own_view=None):
            if regions is not None:
                fields = {
                    "phase": "carousel" if self.frame == 1 else "combat",
                    "hp": 100,
                    "fight_opponent": "Rival",
                }
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
        stored = next(
            event["payload"]
            for event in reversed(events)
            if event["kind"] == "snapshot"
        )
        assert stored["fields"]["recent_opponent_fights_complete"]["value"] is True
        from tft_engine import GameSnapshot

        restored = GameSnapshot.from_dict(stored)
        assert restored.fields["recent_opponent_fights_complete"].value is True
        await runtime.shutdown()

    asyncio.run(scenario())


def test_authenticated_runtime_surfaces_silent_clearing_and_public_modes(tmp_path):
    from websockets.asyncio.client import connect
    from tft_core.messages import Hello, dump

    async def scenario():
        runtime, sessions, data, server = fixture_runtime(tmp_path)
        async with server.listen() as listening:
            async with connect(
                f"ws://127.0.0.1:{listening.sockets[0].getsockname()[1]}"
            ) as ws:
                await ws.send(dump(Hello(token="token")))
                await ws.recv()
                modes = json.loads(await ws.recv())
                assert modes["available_modes"] == ["silent", "baseline"]
                await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
                await wait_snapshot(runtime)
                await ws.send(json.dumps({"v": 1, "type": "request_baseline_state"}))
                while (state := json.loads(await ws.recv()))[
                    "type"
                ] != "baseline_state":
                    pass
                assert state["mode"] == "baseline"
                assert state["content"] is not None
                await ws.send(
                    json.dumps({"v": 1, "type": "set_session_mode", "mode": "silent"})
                )
                while (state := json.loads(await ws.recv()))[
                    "type"
                ] != "baseline_state" or state["mode"] != "silent":
                    pass
                assert state["content"] is None and state["voice"] is None
        await runtime.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize("with_run", [False, True])
def test_completed_permissions_come_from_stored_game_before_mode_reset(
    tmp_path, with_run
):
    async def scenario():
        runtime, sessions, data, server = fixture_runtime(tmp_path)
        sessions.live_installed = True
        if with_run:
            sessions.start_run(
                baseline_fixture(sessions=sessions),
                set_id="18",
            )
        sessions.set_mode("silent")
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        await wait_snapshot(runtime)
        await runtime.update(GameflowUpdate(True, "EndOfGame", "123", "TFT"))
        stored = next(
            game for game in sessions.list_games() if game["game_id"] == "123"
        )
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
            body = json.dumps(
                {"patch": "test.1", "updated": int(time.time() * 1000), "rows": []}
            ).encode()
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
    sources.write_text(
        'schema_version=1\n[statistics]\nminimum_rank="DIAMOND"\nregions="all"\n'
        '[refresh]\nsources=["slow"]\n[sources.slow]\nprovider="metatft"\nkind="statistics"\n'
        'url="https://source-fixture.invalid/rows"\ntimeout=15\n'
    )
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
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            code,
            str(sessions.root),
            str(sessions.config_root),
            str(settings_path),
            str(http.server_port),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
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


def test_encoder_close_deadline_reports_loss_and_stops_its_own_process(tmp_path):
    from datetime import UTC, datetime
    from tft_capture.media import SegmentRecorder
    import psutil

    marker = tmp_path / "encoder-started"
    encoder = tmp_path / "slow_encoder.py"
    encoder.write_text(
        f"import os,time,signal\nfrom pathlib import Path\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nPath({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n"
    )
    sessions = SessionStore(
        tmp_path / "logs", tmp_path / "config", live_installed=False
    )
    sessions.start_game("123")
    recorder = SegmentRecorder(
        sessions, executable=[sys.executable, str(encoder)], close_timeout=0.1
    )
    recorder.submit(Image.new("RGB", (8, 8)), datetime.now(UTC))
    recorder.flush()
    for _ in range(200):
        if marker.exists():
            break
        time.sleep(0.01)
    assert marker.exists()
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="incomplete"):
        recorder.close()
    assert time.monotonic() - started < 1
    assert not recorder.worker.is_alive()
    assert not psutil.pid_exists(int(marker.read_text()))
    assert any(event["kind"] == "video_gap" for event in sessions.read_events("123"))
    assert not any(
        event["kind"] == "video_segment" for event in sessions.read_events("123")
    )


def test_pve_fights_do_not_become_player_opponents_and_unknown_rounds_cannot_certify():
    from tft_core.runtime import project_fight_history

    events = [
        {"kind": "game_start", "timestamp": "2026-10-11T10:00:00+00:00", "payload": {}},
        {
            "kind": "capture_history_start",
            "timestamp": "2026-10-11T10:00:01+00:00",
            "payload": {"round_id": "1-1", "expected_first_round": "1-1"},
        },
        {
            "kind": "fight_start",
            "timestamp": "2026-10-11T10:01:00+00:00",
            "payload": {"round_id": "1-2", "opponent_id": "Neutral monster"},
        },
        {
            "kind": "fight_result",
            "timestamp": "2026-10-11T10:01:30+00:00",
            "payload": {
                "round_id": "1-2",
                "opponent_id": "Neutral monster",
                "result": "win",
            },
        },
    ]
    fields = project_fight_history(
        events,
        "2026-10-11T10:02:00+00:00",
        round_types={"1-1": "carousel", "1-2": "pve"},
    )
    assert fields["recent_opponent_fights"]["value"] == []
    assert fields["recent_opponent_fights_complete"]["value"] is True
    fields = project_fight_history(events, "2026-10-11T10:02:00+00:00", round_types={})
    assert fields["recent_opponent_fights_complete"]["value"] is False


def test_lost_mode_identity_pauses_capture_without_confirming_an_outcome(tmp_path):
    async def scenario():
        devices = Devices()
        runtime, sessions, data, server = fixture_runtime(tmp_path, devices=devices)
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        await wait_snapshot(runtime)
        await runtime.update(GameflowUpdate(True, "InProgress", "123", None))
        assert devices.closed.is_set()
        assert runtime.latest_snapshot is None
        assert sessions.active_game_id == "123"
        assert not any(
            event["kind"] == "game_end" for event in sessions.read_events("123")
        )
        assert any(
            event["kind"] == "capture_gap" for event in sessions.read_events("123")
        )
        await runtime.update(GameflowUpdate(True, "Reconnect", "123", "TFT"))
        await wait_snapshot(runtime)
        assert devices.opens == 2
        await runtime.shutdown()

    asyncio.run(scenario())


def test_malformed_lcu_phase_is_reported_as_unavailable():
    from tft_capture.lcu import LcuUnavailable

    async def scenario():
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"unexpected": "phase"})
        )
        async with LcuConnection(
            LcuCredentials(1, "fixture-token"), transport=transport
        ) as lcu:
            with pytest.raises(LcuUnavailable, match="Malformed gameflow phase"):
                await lcu.get_phase()

    asyncio.run(scenario())


def test_native_close_failure_is_durable_and_does_not_end_the_game(tmp_path):
    class FailingClose(Devices):
        def close(self):
            raise RuntimeError("recorded source close failed")

    async def scenario():
        runtime, sessions, data, server = fixture_runtime(
            tmp_path, devices=FailingClose()
        )
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        await wait_snapshot(runtime)
        await runtime.update(GameflowUpdate(True, "EndOfGame", "123", "TFT"))
        events = sessions.read_events("123")
        assert sessions.active_game_id == "123"
        assert not any(event["kind"] == "game_end" for event in events)
        assert any(event["kind"] == "capture_finalization_failed" for event in events)
        assert "close failed" in runtime.status
        await runtime.update(GameflowUpdate(True, "InProgress", "456", "TFT"))
        assert sessions.active_game_id == "123"
        assert sessions.read_events("456") == []
        await runtime.shutdown()

    asyncio.run(scenario())


def test_runtime_settings_pin_calibrated_digit_assets_and_reject_missing_path(tmp_path):
    from tft_core.runtime import RuntimeSettings

    fixture_runtime(tmp_path)
    path = tmp_path / "settings.toml"
    original = path.read_text().replace('digits="calibrated-glyphs"\n', "")
    path.write_text(original)
    with pytest.raises(ValueError, match="documented capture fields"):
        RuntimeSettings.load(path)
    path.write_text(original + 'digits="calibrated-glyphs"\n')
    settings = RuntimeSettings.load(path)
    assert settings.digits == (tmp_path / "calibrated-glyphs").resolve()


def test_core_reports_and_recovers_from_external_lcu_discovery_failure(tmp_path):
    from tft_core.app import run
    from tft_core.messages import Hello, dump
    from websockets.asyncio.client import connect
    import contextlib
    import io

    runtime, sessions, data, server = fixture_runtime(tmp_path)
    closed = asyncio.Event()
    attempts = 0

    def discover():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("recorded process enumeration failure")
        return None

    async def scenario():
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            task = asyncio.create_task(
                run(
                    "fixture-token",
                    sessions=sessions,
                    data_store=data,
                    settings_path=tmp_path / "settings.toml",
                    closed=closed,
                    watcher_options={"discover": discover, "discovery_interval": 0.01},
                )
            )
            try:
                for _ in range(200):
                    if output.getvalue():
                        break
                    await asyncio.sleep(0.01)
                port = json.loads(output.getvalue().splitlines()[0])["port"]
                async with connect(f"ws://127.0.0.1:{port}") as ws:
                    await ws.send(dump(Hello(token="fixture-token")))
                    await ws.send(
                        json.dumps({"v": 1, "type": "request_baseline_state"})
                    )
                    for _ in range(10):
                        state = json.loads(await asyncio.wait_for(ws.recv(), 1))
                        if state["type"] == "baseline_state":
                            assert (
                                "Watcher unavailable: RuntimeError" in state["status"]
                            )
                            assert state["content"] is None
                            break
                for _ in range(200):
                    if attempts >= 2:
                        break
                    await asyncio.sleep(0.01)
                assert attempts >= 2
            finally:
                closed.set()
                await task

    asyncio.run(scenario())


def test_failed_capture_clears_pending_handoff_before_future_dispatch(tmp_path):
    async def scenario():
        devices = Devices()
        runtime, sessions, data, server = fixture_runtime(tmp_path, devices=devices)
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        await wait_snapshot(runtime)
        devices.failure = True
        try:
            for _ in range(200):
                if "driver failed" in runtime.status:
                    break
                await asyncio.sleep(0.01)
            assert "driver failed" in runtime.status
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(runtime.next_snapshot(), 0.05)
        finally:
            await runtime.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize("game_id,mode", [(None, None), ("999", "TFT")])
def test_unconfirmed_terminal_identity_pauses_and_retains_an_unfinished_log(
    tmp_path, game_id, mode
):
    async def scenario():
        devices = Devices()
        runtime, sessions, data, server = fixture_runtime(tmp_path, devices=devices)
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        await wait_snapshot(runtime)
        try:
            await runtime.update(GameflowUpdate(True, "EndOfGame", game_id, mode))
            assert devices.closed.is_set()
            assert runtime.latest_snapshot is None
            assert sessions.active_game_id == "123"
            events = sessions.read_events("123")
            assert not any(event["kind"] == "game_end" for event in events)
            assert any(event["kind"] == "capture_gap" for event in events)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(runtime.next_snapshot(), 0.05)
        finally:
            await runtime.shutdown()

    asyncio.run(scenario())


def test_runtime_settings_accept_an_operator_checked_window_title(tmp_path):
    from tft_core.runtime import RuntimeSettings

    fixture_runtime(tmp_path)
    path = tmp_path / "settings.toml"
    original = path.read_text()
    path.write_text(
        original.replace('window_title="fixture-window"\n', "")
        + 'window_title="Owner-reviewed game title"\n'
    )
    assert RuntimeSettings.load(path).window_title == "Owner-reviewed game title"


def test_invalid_refresh_configuration_remains_visible_with_last_good_capture(tmp_path):
    from dataclasses import replace
    from tft_core.runtime import CaptureRuntime

    async def scenario():
        original, sessions, data, server = fixture_runtime(tmp_path)
        runtime = CaptureRuntime(
            server,
            sessions,
            data,
            settings=replace(
                original.settings, sources=tmp_path / "missing-sources.toml"
            ),
            devices=Devices(),
        )
        try:
            await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
            await wait_snapshot(runtime)
            state = server.baseline.state("baseline")
            assert "Refresh configuration unavailable" in state.status
        finally:
            await runtime.shutdown()

    asyncio.run(scenario())


def test_queued_capture_callbacks_cannot_deliver_after_source_failure(tmp_path):
    class QueuedFailure(Devices):
        def __init__(self):
            super().__init__()
            self.frames = 0

        def capture(self):
            self.frames += 1
            if self.frames > 1:
                raise RuntimeError("recorded queued source failure")
            return super().capture()

    async def scenario():
        devices = QueuedFailure()
        runtime, sessions, data, server = fixture_runtime(tmp_path, devices=devices)
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        try:
            # Keep the core loop busy until both the first frame callback and
            # failure callback are queued by the actual capture thread.
            assert devices.closed.wait(2)
            for _ in range(200):
                if "queued source failure" in runtime.status:
                    break
                await asyncio.sleep(0.01)
            assert "queued source failure" in runtime.status
            assert runtime.latest_snapshot is None
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(runtime.next_snapshot(), 0.05)
        finally:
            await runtime.shutdown()

    asyncio.run(scenario())


def test_unknown_loss_can_detach_for_new_game_and_reattach_original_pins(tmp_path):
    async def scenario():
        runtime, sessions, data, server = fixture_runtime(tmp_path)
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        await wait_snapshot(runtime)
        sessions.set_mode("silent")
        original = sessions.read_events("123")[0]
        old_names = runtime.settings.names.read_text()
        await runtime.update(GameflowUpdate(False, None))
        entities = runtime.settings.patch_dir / "entities.json"
        entities.write_text(
            entities.read_text().replace(
                "Reaches the backline", "Recorded updated fixture text"
            )
        )
        new_pin = data.refresh(runtime.settings.patch_dir).snapshot
        assert new_pin.snapshot_id != original["payload"]["data_snapshot_id"]
        names = json.loads(old_names)
        names["snapshot_id"] = new_pin.snapshot_id
        runtime.settings.names.write_text(json.dumps(names))
        try:
            await runtime.update(GameflowUpdate(True, "Lobby", "456", "TFT"))
            await runtime.update(GameflowUpdate(True, "InProgress", "456", "TFT"))
            current = await wait_snapshot(runtime)
            assert current["game_id"] == "456"
            assert current["data_snapshot_id"] == new_pin.snapshot_id
            assert sessions.mode.value == "baseline"
            assert sessions.read_events("123")[0] == original
            assert not any(
                event["kind"] == "game_end" for event in sessions.read_events("123")
            )
            await runtime.update(GameflowUpdate(False, None))
            runtime.settings.names.write_text(old_names)
            await runtime.update(GameflowUpdate(True, "Reconnect", "123", "TFT"))
            restored = await wait_snapshot(runtime)
            assert (
                restored["data_snapshot_id"] == original["payload"]["data_snapshot_id"]
            )
            assert sessions.mode.value == "silent"
            assert (
                sum(
                    event["kind"] == "game_start"
                    for event in sessions.read_events("123")
                )
                == 1
            )
            assert not any(
                event["kind"] == "game_end" for event in sessions.read_events("456")
            )
        finally:
            await runtime.shutdown()

    asyncio.run(scenario())


def test_old_queued_failure_cannot_clear_the_new_games_first_snapshot(tmp_path):
    class OldSource(Devices):
        def __init__(self):
            super().__init__()
            self.writer_exited = threading.Event()

        def capture(self):
            raise RuntimeError("recorded old-game failure")

        def close(self):
            super().close()
            writer = threading.current_thread()

            def confirm_exit():
                writer.join()
                self.writer_exited.set()

            threading.Thread(target=confirm_exit, daemon=True).start()

    class NewSource(Devices):
        def __init__(self):
            super().__init__()
            self.frames = 0
            self.pending = threading.Event()
            self.release = threading.Event()

        def capture(self):
            self.frames += 1
            if self.frames > 1:
                self.pending.set()
                self.release.wait(5)
            return super().capture()

    old, new = OldSource(), NewSource()

    class ExternalDevices:
        def __init__(self):
            self.opens = 0

        def open(self, settings, data):
            self.opens += 1
            source = old if self.opens == 1 else new
            return source, source, None

    async def scenario():
        runtime, sessions, data, server = fixture_runtime(
            tmp_path, devices=ExternalDevices()
        )
        await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
        try:
            assert old.writer_exited.wait(
                2
            )  # All old writes ended; its callback remains queued.
            await runtime.update(GameflowUpdate(True, "InProgress", "456", "TFT"))
            assert new.pending.wait(2)  # First new-frame callback is also queued.
            snapshot = await wait_snapshot(runtime)
            assert snapshot["game_id"] == "456"
            assert "old-game failure" not in runtime.status
            assert (await asyncio.wait_for(runtime.next_snapshot(), 1))[
                "game_id"
            ] == "456"
            assert not any(
                event["kind"] == "game_end" for event in sessions.read_events("123")
            )
            assert not any(
                event["kind"] == "capture_status"
                and "old-game failure" in event["payload"].get("error", "")
                for event in sessions.read_events("456")
            )
        finally:
            new.release.set()
            await runtime.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize("missing", ["data", "model_pointer", "settings"])
@pytest.mark.parametrize("safe_phase", ["EndOfGame", "Lobby"])
def test_positive_game_gates_blocked_startup_refresh_even_when_capture_cannot_start(
    tmp_path, missing, safe_phase
):
    from datetime import UTC, datetime
    from tft_core.runtime import CaptureRuntime
    from tft_data.refresh import RefreshCoordinator
    from tft_data.sources import SourceMetadata

    entered, release = threading.Event(), threading.Event()

    class SlowSource:
        name = "recorded-slow-source"
        kind = "statistics"

        def metadata(self):
            entered.set()
            assert release.wait(5)
            return SourceMetadata("test.1", datetime.now(UTC))

        def fetch(self):
            return {"rows": []}

    async def scenario():
        prepared, sessions, previous, server = fixture_runtime(tmp_path)
        data = (
            previous
            if missing == "model_pointer"
            else DataStore(tmp_path / "empty-snapshots")
        )
        settings = None if missing == "settings" else prepared.settings
        if missing == "model_pointer":
            settings.model_pointer.unlink()
        initial = data.current
        runtime = CaptureRuntime(
            server, sessions, data, settings=settings, devices=Devices()
        )
        # Use the real coordinator; only the external source response is recorded.
        runtime.refresh = RefreshCoordinator(
            data, prepared.settings.patch_dir, sources=[SlowSource()]
        )
        try:
            await runtime.start()
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set()
            await runtime.update(GameflowUpdate(True, "InProgress", "123", "TFT"))
            assert sessions.active_game_id is None
            release.set()
            await runtime.refresh.wait()
            assert data.current is initial
            assert runtime.refresh.in_game is True
            await runtime.update(GameflowUpdate(False, None))
            assert data.current is initial
            assert runtime.refresh.in_game is True
            await runtime.update(GameflowUpdate(True, "EndOfGame", "999", "TFT"))
            assert data.current is initial
            assert runtime.refresh.in_game is True
            await runtime.update(GameflowUpdate(True, safe_phase, "123", "TFT"))
            await runtime.refresh.wait()
            assert data.current is not None
            assert runtime.refresh.in_game is False
            assert sessions.read_events("123") == []
        finally:
            release.set()
            await runtime.shutdown()

    asyncio.run(scenario())


def test_native_finalization_immediately_retires_capture_publication(tmp_path):
    class ClosingDevices(Devices):
        def __init__(self):
            super().__init__()
            self.closing = threading.Event()
            self.release = threading.Event()

        def close(self):
            self.closing.set()
            self.release.wait(2)
            super().close()

    async def scenario():
        devices = ClosingDevices()
        runtime, sessions, data, server = fixture_runtime(tmp_path, devices=devices)
        await runtime.update(GameflowUpdate(True, 'InProgress', '123', 'TFT'))
        await wait_snapshot(runtime)
        generation = runtime.publication_generation
        ending = asyncio.create_task(runtime.update(GameflowUpdate(True, 'EndOfGame', '123', 'TFT')))
        try:
            for _ in range(200):
                if devices.closing.is_set():
                    break
                await asyncio.sleep(.005)
            assert devices.closing.is_set()
            assert runtime.latest_snapshot is None
            assert runtime.publication_generation != generation
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(runtime.next_snapshot(), .02)
        finally:
            devices.release.set()
            await ending
            await runtime.shutdown()
        assert sessions.list_games()[0]['finished'] is True

    asyncio.run(scenario())


def test_clean_checkout_missing_settings_names_the_required_local_setup(tmp_path):
    import pytest
    from tft_core.runtime import RuntimeSettings

    missing = tmp_path / 'config' / 'settings.toml'
    with pytest.raises(ValueError) as failure:
        RuntimeSettings.load(missing)
    message = str(failure.value)
    assert str(missing) in message
    assert 'docs/agents/runtime-boundary.md' in message
    assert 'reviewed capture inputs' in message
    assert not missing.exists()


def test_blocked_client_discovery_does_not_hold_core_exit(tmp_path):
    """A process enumeration stuck in the OS must not outlive the shell close."""
    entered = tmp_path / "discovery-entered"
    code = """
import asyncio, sys, threading
from pathlib import Path
from tft_core.app import run
from tft_core.storage import SessionStore
def blocked_discovery():
    Path(sys.argv[3]).write_text('entered')
    threading.Event().wait()
asyncio.run(run('fixture-token', sessions=SessionStore(Path(sys.argv[1]),Path(sys.argv[2]),live_installed=False),settings_path=Path(sys.argv[1])/'missing.toml',watcher_options={'discover':blocked_discovery}))
"""
    child = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path / "logs"), str(tmp_path / "config"), str(entered)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert json.loads(child.stdout.readline())["event"] == "ready"
        deadline = time.monotonic() + 3
        while not entered.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert entered.exists()
        started = time.monotonic()
        child.stdin.close()
        child.wait(timeout=5)
        assert child.returncode == 0, child.stderr.read()
        assert time.monotonic() - started < 5
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
