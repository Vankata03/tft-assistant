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
async def core(tmp_path, client, *, live_installed=True, devices=None, prepare=None, **options):
    from tft_core.app import run

    _, sessions, data, _ = fixture_runtime(tmp_path)
    if prepare is not None:
        data = prepare(tmp_path)
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


@pytest.mark.parametrize("failure", ["new-pin", "disk-failure", "history-read"])
def test_actual_app_preserves_accepted_pin_when_engine_work_fails(tmp_path, monkeypatch, failure):
    import hashlib
    import os
    import threading
    import tomllib
    import tomli_w
    from PIL import Image
    from tft_capture.ocr import TextLine
    from tft_capture.windows import CapturedFrame
    from tests.test_replay_contracts import historical_data
    from pathlib import Path

    superseded = failure == "new-pin"

    # Explicitly synthetic external HUD artwork and OCR. Real capture recognizes
    # all empty unit slots; real data refresh supplies the scored Guide/Lines.
    image = Image.new("RGB", (100, 100), "white")
    for x in range(50):
        for y in range(100):
            image.putpixel((x, y), (30, 60, 90))

    def prepare(root):
        (root / "planning").mkdir()
        store, _ = historical_data(root / "planning")
        patch = root / "planning" / "patch"
        static_path = patch / "static.toml"
        static = tomllib.loads(static_path.read_text())
        static["fields"]["capture_unit_counter"] = {
            "value": {"region": "unit_count", "semantic": "physical_units"},
            "source": "owner", "citation": "Synthetic empty-slot counter fixture; no HUD qualification",
        }
        static_path.write_text(tomli_w.dumps(static))
        data = store.refresh(patch).snapshot
        settings = tomllib.loads((root / "settings.toml").read_text())
        settings.update(expected_patch="fixture", patch_dir=str(patch))
        (root / "settings.toml").write_text(tomli_w.dumps(settings))
        (root / "names.json").write_text(json.dumps({
            "snapshot_id": data.snapshot_id, "locale": "en_us",
            "names": {"units": {"unit": "Fixture unit"}},
        }))
        image.save(root / "empty.png")
        asset = {"file": "empty.png", "sha256": hashlib.sha256((root / "empty.png").read_bytes()).hexdigest()}
        regions = {name: [0, 0, 1, 1] for name in (
            "stage", "players", "gold", "level", "xp", "streak", "phase", "scouted", "unit_count", "board", "bench",
        )}
        (root / "profile.json").write_text(json.dumps({
            "version": 1, "regions": regions,
            "slot_templates": {"_empty": asset},
            "unit_slots": [{"zone": zone, "position": index, "box": [0, 0, 1, 1]}
                           for zone, count in (("board", 28), ("bench", 9)) for index in range(count)],
            "signals": [{"field": "trait_panel_empty", "region": "board", "box": [0, 0, 1, 1],
                         "templates": {"true": asset}}],
        }))
        return store

    class PlanningDevices(Devices):
        def __init__(self):
            super().__init__()
            self.frames = threading.Semaphore(1)
            self.frame = 0

        def capture(self):
            if not self.frames.acquire(timeout=15):
                raise RuntimeError("Synthetic window frame timed out")
            self.frame += 1
            return CapturedFrame(image.copy(), "window-a", "recorded")

        def read(self, image, *, region):
            if region == "players":
                return [TextLine(f"{'Owner' if index == 0 else f'Player{index}'} 60", 1,
                                 (0, index / 8, 1, (index + 1) / 8)) for index in range(8)]
            text = {"stage": "3-2", "gold": str(28 + self.frame), "level": "1", "xp": "0/2",
                    "streak": "0", "phase": "planning", "scouted": "Owner Level 1", "unit_count": "0/1"}.get(region)
            return [TextLine(text, 1)] if text else []

    entered, release, flushed = threading.Event(), threading.Event(), threading.Event()
    original = os.fsync
    hold = False
    fail_read = False
    read_failed = threading.Event()
    original_read = Path.read_bytes

    def read_bytes(path):
        nonlocal fail_read
        if fail_read and threading.current_thread().name == "engine-latest" and path.name == "events.jsonl":
            fail_read = False
            read_failed.set()
            raise OSError("Synthetic historical log read failure")
        return original_read(path)

    def flush(fd):
        nonlocal hold
        if hold and threading.current_thread().name.startswith("tft-io-"):
            hold = False
            entered.set()
            if not release.wait(3):
                raise OSError("Synthetic disk flush timed out")
            result = original(fd)
            flushed.set()
            if not superseded:
                raise OSError("Synthetic disk flush failure")
            return result
        return original(fd)

    @contextlib.asynccontextmanager
    async def release_capture(devices):
        try:
            yield
        finally:
            # Unblock external capture before the app waits for native shutdown,
            # including when an assertion fails inside the context.
            release.set()
            for _ in range(100):
                devices.frames.release()

    async def scenario():
        nonlocal hold, fail_read
        client, devices = ScriptedClient(), PlanningDevices()
        monkeypatch.setattr(os, "fsync", flush)
        monkeypatch.setattr(Path, "read_bytes", read_bytes)
        async with core(tmp_path, client, devices=devices, prepare=prepare) as (ws, sessions, _, _), release_capture(devices):
            await receive_until(ws, lambda m: m["type"] == "gameflow" and m["phase"] == "Lobby")
            await ws.send(json.dumps({"v": 1, "type": "set_session_mode", "mode": "live"}))
            await receive_until(ws, lambda m: m["type"] == "session_mode" and m["mode"] == "live")
            client.phase, client.game_id, client.mode = "InProgress", "123", "TFT"
            await ws.send(json.dumps({"v": 1, "type": "request_live_state"}))
            first, _ = await receive_until(ws, lambda m: m["type"] == "live_state" and bool((m.get("content") or {}).get("lines")), seconds=15)
            line = first["content"]["lines"][0]
            pin = {"v": 1, "type": "pin_line", "game_id": "123", "revision": first["revision"],
                   "comp_id": line["comp_id"], "line_id": line["line_id"], "seed": line["seed"]}
            if not superseded:
                await ws.send(json.dumps(pin))
                pinned, _ = await receive_until(ws, lambda m: m["type"] == "live_state" and bool(m.get("pin")))
            if failure == "history-read":
                fail_read = True
                devices.frames.release()
                # Either the erroneous cleared state or the corrected visible
                # error confirms that the owning loop consumed the failed read.
                notice, _ = await receive_until(ws, lambda m:
                    (m["type"] == "error" and m["code"] == "engine_evaluation_unavailable")
                    or (m["type"] == "live_state" and "Synthetic historical log read failure" in m["status"]))
                assert read_failed.is_set()
            else:
                hold = True
                devices.frames.release()
                async with asyncio.timeout(2):
                    while not entered.is_set():
                        await asyncio.sleep(.002)
                if superseded:
                    await ws.send(json.dumps(pin))
                    pinned, _ = await receive_until(ws, lambda m: m["type"] == "live_state" and bool(m.get("pin")))
                assert pinned["pin"]["line_id"] == line["line_id"]
                release.set()
                async with asyncio.timeout(2):
                    while not flushed.is_set():
                        await asyncio.sleep(.002)
                if superseded:
                    await asyncio.sleep(.05)
                else:
                    error, _ = await receive_until(ws, lambda m: m["type"] == "error" and m["code"] == "engine_publication_unavailable")
                    assert "Synthetic disk flush failure" in error["message"]
            await ws.send(json.dumps({"v": 1, "type": "request_live_state"}))
            after, _ = await receive_until(ws, lambda m: m["type"] == "live_state")
            assert after["pin"] == pinned["pin"]
            assert after["revision"] == first["revision"]
            assert after["content"] == first["content"]
            if failure == "history-read":
                assert notice["code"] == "engine_evaluation_unavailable"
                assert "Synthetic historical log read failure" in notice["message"]
            assert not any(e["kind"] == "session_controls_reset" for e in sessions.read_events("123"))

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
            # Manual regeneration uses this actual app's owned review supervisor.
            async def request_review(request_id, operation, **arguments):
                await ws.send(json.dumps({'v': 1, 'type': 'request_review', 'request_id': request_id,
                    'game_id': '123', 'operation': operation, 'report_id': ready['report_id'],
                    'evidence_id': ready['evidence_id'], **arguments}))
                response, _ = await receive_until(ws, lambda m: m.get('request_id') == request_id)
                assert response['type'] == 'review_response', response
                return response['value']
            point = await request_review('moment-id', 'page', path=['moments', 0, 'moment_id'])
            moment_id = point['items'][0]['value']
            await request_review('owner-tag', 'tag', moment_id=moment_id, tag='unsure')
            before_log = sessions.log_path('123').read_bytes()
            queued = await request_review('regenerate', 'regenerate')
            assert queued['state'] == 'queued'
            regenerated, _ = await receive_until(ws, lambda m: m['type'] == 'review_ready', seconds=20)
            assert regenerated['report_id'] == ready['report_id']
            summary = await request_review('new-summary', 'summary')
            assert summary['tags'][moment_id] == 'unsure'
            assert sessions.log_path('123').read_bytes() == before_log

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
