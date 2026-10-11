"""One serialized owner of capture, immutable game pins and safe refresh."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import subprocess
import sys
import threading
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from tft_capture.layout import HudLayout
from tft_capture.ocr import NameCatalog, RapidOCRReader
from tft_capture.pipeline import CapturePipeline
from tft_capture.profile import load_profile
from tft_capture.runner import CaptureRunner
from tft_data import DataError
from tft_data.refresh import RefreshCoordinator
from tft_data.source_config import SourceConfiguration

log = logging.getLogger(__name__)
SHUTDOWN_SECONDS = 8.0


def project_fight_history(events, captured_at):
    """Certify only an uninterrupted causal log prefix, retaining encounter times."""
    now = datetime.fromisoformat(captured_at)
    if now.tzinfo is None:
        raise ValueError("Fight history requires a timezone-bearing capture time")
    rows, pending = [], {}
    complete = False
    started = False
    invalidated = False
    for event in events:
        at = datetime.fromisoformat(event["timestamp"])
        if at.tzinfo is None:
            raise ValueError("Fight history contains a timestamp without timezone")
        if at > now:
            continue
        kind, payload = event["kind"], event["payload"]
        if kind == "game_start" and not started:
            started = True
        elif kind == "capture_history_start" and started and not invalidated:
            complete = bool(payload.get("round_id") and payload.get("round_id") == payload.get("expected_first_round"))
        elif kind in {"capture_gap", "capture_shutdown_timeout", "fight_incomplete", "capture_history_gap"}:
            complete = False
            invalidated = True
        elif kind == "capture_status" and payload.get("state") == "unavailable":
            complete = False
            invalidated = True
        elif kind == "fight_start":
            identity, round_id = payload.get("opponent_id"), payload.get("round_id")
            if not started or not isinstance(identity, str) or not identity or not isinstance(round_id, str) or not round_id or round_id in pending:
                complete = False
                continue
            row = {"opponent_id": identity, "round_id": round_id, "read_at": event["timestamp"]}
            pending[round_id] = row
        elif kind == "fight_result":
            row = pending.pop(payload.get("round_id"), None)
            if not row or row["opponent_id"] != payload.get("opponent_id") or payload.get("result") not in {"win", "loss", "draw"}:
                complete = False
                continue
            rows.append({**row, "result_read_at": event["timestamp"], "result": payload["result"]})
    field = {"read_at": captured_at, "source": "log_projection", "confidence": 1.0}
    return {"recent_opponent_fights": {**field, "value": rows},
        "recent_opponent_fights_complete": {**field, "value": bool(started and complete and not pending)}}


@dataclass(frozen=True)
class RuntimeSettings:
    owner_name: str
    locale: str
    expected_patch: str
    profile: Path
    game_config: Path
    models: Path
    model_pointer: Path
    names: Path
    patch_dir: Path
    sources: Path | None = None
    overrides: Path | None = None
    foot_offsets: Path | None = None

    @classmethod
    def load(cls, path):
        path = Path(path)
        try:
            raw = tomllib.loads(path.read_text())
            required = {"owner_name", "locale", "expected_patch", "profile", "game_config",
                "models", "model_pointer", "names", "patch_dir"}
            optional = {"sources", "overrides", "foot_offsets"}
            if raw.pop("schema_version", None) != 1 or set(raw) - required - optional or required - set(raw):
                raise ValueError("settings require schema_version=1 and the documented capture fields")
            if any(not isinstance(value, str) or not value.strip() for value in raw.values()):
                raise ValueError("runtime settings must be nonempty strings")
            for key in (required | optional) - {"owner_name", "locale", "expected_patch"}:
                if key in raw:
                    raw[key] = (path.parent / raw[key]).resolve()
            return cls(**raw)
        except (OSError, ValueError, TypeError) as error:
            raise ValueError(f"Capture settings unavailable: {path}: {error}") from None


class NativeDevices:
    """Local, CPU-only native readers; capture never prepares or downloads assets."""

    def open(self, settings, data):
        if sys.platform != "win32":
            raise RuntimeError("Production window capture requires Windows; offline replay remains available")
        from tft_capture.board_reader import BoardReader
        from tft_capture.windows import WindowsCaptureSource

        profile = load_profile(settings.profile)
        board = BoardReader.from_version(settings.models, pointer=settings.model_pointer,
            data=data, templates=profile.reader.items, foot_offsets=settings.foot_offsets)
        return WindowsCaptureSource(), RapidOCRReader.from_bundled_models(), board


def engine_identity():
    """Record the checked-out implementation, including dirty working trees."""
    try:
        root = Path(__file__).resolve().parents[3]
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
            capture_output=True, text=True, check=True, timeout=2).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root,
            capture_output=True, text=True, check=True, timeout=2).stdout.strip()
        return commit + ("+dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"


class _CaptureWorker:
    def __init__(self, settings, data, sessions, devices, callback, failure_callback, *, original=None):
        self.settings, self.data, self.sessions, self.devices = settings, data, sessions, devices
        self.callback, self.failure_callback = callback, failure_callback
        self.original = original or {}
        self.game_id = sessions.active_game_id
        self.stop_requested = threading.Event()
        self.done = threading.Event()
        self.runner = None
        self.error = None
        self.thread = threading.Thread(target=self._run, name="tft-capture", daemon=True)

    def _run(self):
        pipeline = None
        source = None
        try:
            settings = self.settings
            layout = HudLayout.from_config(settings.game_config)
            if layout.window_mode not in {"windowed", "borderless"}:
                raise ValueError("Capture requires a checked windowed or borderless game configuration")
            names = json.loads(settings.names.read_text())
            if names.get("snapshot_id") != self.data.snapshot_id or names.get("locale") != settings.locale:
                raise ValueError("Client-locale names must identify the original pinned data snapshot and locale")
            catalog = names.get("names", {})
            required = {entity.id for entity in self.data.entities.values() if entity.kind == "unit"}
            if not required or not required <= set(catalog.get("units", {})):
                raise ValueError("Client-locale names are missing pinned playable units")
            if any(identity not in self.data.entities or not isinstance(name, str) or not name.strip()
                for entries in catalog.values() for identity, name in entries.items()):
                raise ValueError("Client-locale names contain invalid identities or empty names")
            pointer = json.loads(settings.model_pointer.read_text())
            if self.original.get("model_version") != pointer.get("version"):
                raise ValueError("Resume capture with the original pinned model version")
            profile = load_profile(settings.profile)
            history = self.sessions.read_events(self.game_id)
            old_profiles = {event["payload"]["sha256"] for event in history if event["kind"] == "capture_profile"}
            if old_profiles and old_profiles != {profile.sha256}:
                raise ValueError("Resume capture with the original reviewed profile")
            pointer_hash = hashlib.sha256(settings.model_pointer.read_bytes()).hexdigest()
            old_pointers = {event["payload"]["model_pointer_sha256"] for event in history
                if event["kind"] == "capture_profile" and event["payload"].get("model_pointer_sha256")}
            if old_pointers and old_pointers != {pointer_hash}:
                raise ValueError("Resume capture with the original reviewed model pointer")
            source, ocr, board = self.devices.open(settings, self.data)
            profile = load_profile(settings.profile, board_reader=board,
                carousel_classifier=board.units if board else None,
                unit_ids={name: identity for identity, name in catalog["units"].items()})
            self.sessions.append_event("capture_profile", {"sha256": profile.sha256,
                "locale": settings.locale, "model_version": pointer["version"], "model_pointer_sha256": pointer_hash})
            video = None
            if self.sessions.media_mode == "full_video":
                from tft_capture.media import SegmentRecorder
                video = SegmentRecorder(self.sessions)
            pipeline = CapturePipeline.from_data(self.game_id, data=self.data, ocr=ocr,
                sink=self.sessions, catalog=NameCatalog(catalog), layout=layout,
                visual_reader=profile.reader, regions=profile.regions,
                own_player_name=settings.owner_name, tracking_events=history, video=video)
            self.runner = CaptureRunner(source, pipeline)
            if self.stop_requested.is_set():
                self.runner.stop()
            first_round = None
            calibrated = False
            coverage_checked = any(event["kind"] in {"snapshot", "capture_history_start", "capture_history_gap", "capture_gap"} for event in history)
            coverage_invalid = any(event["kind"] in {"capture_gap", "capture_history_gap", "fight_incomplete"} for event in history)
            last_capture = None

            def publish(snapshot):
                nonlocal first_round, calibrated, coverage_checked, coverage_invalid, last_capture
                round_id = snapshot.get("round_id")
                if round_id and first_round is None:
                    first_round = round_id
                elif round_id and round_id != first_round and not calibrated:
                    pipeline.finish_calibration_round()
                    calibrated = True
                at = datetime.fromisoformat(snapshot["captured_at"])
                fields = snapshot.get("fields", {})
                fresh = {key: field["value"] for key, field in fields.items()
                    if field.get("read_at") and 0 <= (at - datetime.fromisoformat(field["read_at"])).total_seconds() <= 2}
                if not coverage_checked:
                    schedule = self.data.static.get("round_order")
                    first = schedule.value[0] if schedule and schedule.value else None
                    if first and fresh.get("round") == first and fresh.get("phase") in {"planning", "carousel", "combat"}:
                        self.sessions.append_event("capture_history_start", {"round_id": first,
                            "expected_first_round": first, "data_snapshot_id": self.data.snapshot_id,
                            "source": "pinned-round-order+observed-initial-round"}, timestamp=snapshot["captured_at"])
                    else:
                        coverage_invalid = True
                        self.sessions.append_event("capture_history_gap", {"reason": "initial_round_not_observed"}, timestamp=snapshot["captured_at"])
                    coverage_checked = True
                readable = fresh.get("phase") in {"planning", "roll_down", "augment", "carousel", "combat", "end"}
                if fresh.get("phase") == "combat":
                    readable = readable and bool(fresh.get("fight_opponent")) and "hp" in fresh and bool(fresh.get("round"))
                if not coverage_invalid and (not readable or (last_capture and (at - last_capture).total_seconds() > 2)):
                    coverage_invalid = True
                    self.sessions.append_event("capture_history_gap", {"reason": "fight_phase_coverage_unavailable"}, timestamp=snapshot["captured_at"])
                last_capture = at
                projection = project_fight_history(self.sessions.read_events(self.game_id), snapshot["captured_at"])
                snapshot = {**snapshot, "fields": {**snapshot.get("fields", {}), **projection}}
                self.callback(snapshot)

            self.runner.run(on_snapshot=publish)
        except Exception as error:
            self.error = f"Capture unavailable: {type(error).__name__}: {error}"
            self.failure_callback(self.error)
            try:
                self.sessions.append_event("capture_status", {"state": "unavailable", "error": self.error})
            except Exception:
                log.exception("Unable to persist capture failure")
        finally:
            try:
                if source:
                    source.close()
            except Exception as error:
                self.error = f"Capture source close failed: {error}"
                self.failure_callback(self.error)
                log.exception("Capture source close failed")
            try:
                if pipeline:
                    pipeline.finish_calibration_round()
                    pipeline.close()
            except Exception as error:
                self.error = f"Capture finalization failed: {type(error).__name__}: {error}"
                self.failure_callback(self.error)
                log.exception("Capture finalization failed")
            self.done.set()

    def stop(self):
        self.stop_requested.set()
        if self.runner:
            self.runner.stop()


class CaptureRuntime:
    """LCU updates, refresh and finalization share one asynchronous lifecycle lock.

    ``devices`` is the native OCR/window boundary. Tests feed recorded external
    devices through the same CaptureRunner, CapturePipeline and SessionStore.
    """

    def __init__(self, server, sessions, data_store, *, settings=None, settings_error=None,
                 devices=None, shutdown_seconds=SHUTDOWN_SECONDS):
        self.server, self.sessions, self.data_store = server, sessions, data_store
        self.settings, self.devices = settings, devices or NativeDevices()
        self.status = settings_error or "Capture waiting for a positively identified TFT game"
        self.shutdown_seconds = shutdown_seconds
        self.latest_snapshot = None
        self.completed_game = None
        self.worker = None
        self.pinned_data = None
        self._lock = asyncio.Lock()
        self._closed = False
        self._handoff = asyncio.Queue(maxsize=1)
        self._loop = None
        self._incoming_lock = threading.Lock()
        self._incoming = None
        self._incoming_scheduled = False
        self._resume_task = None
        self._last_update = None
        self._refresh_task = None
        self._engine_version = engine_identity()
        self.refresh = None
        if settings:
            try:
                options = {"overrides": settings.overrides}
                if settings.sources:
                    configured = SourceConfiguration.load(settings.sources)
                    options.update(sources=configured.sources, fallback=configured.fallback)
                self.refresh = RefreshCoordinator(data_store, settings.patch_dir, **options)
            except (DataError, OSError, ValueError) as error:
                self.status = f"Refresh configuration unavailable: {error}"

    async def start(self):
        self._loop = asyncio.get_running_loop()
        self._publish()
        self._trigger_refresh("startup")

    def _trigger_refresh(self, reason):
        if self.refresh:
            task = self.refresh.trigger(reason)
            if task and task is not self._refresh_task:
                self._refresh_task = task
                task.add_done_callback(self._refreshed)

    def _refreshed(self, task):
        if task.cancelled():
            return
        try:
            result = task.result()
            if result.warnings:
                self.status = "; ".join(result.warnings)
            elif not self.sessions.active_game_id:
                self.status = "Data ready; waiting for a positively identified TFT game"
        except Exception as error:
            self.status = f"Data refresh unavailable: {error}"
            log.exception("Data refresh failed")
        if not self._closed:
            self._publish()
            if self._last_update and self._last_update.phase in {"InProgress", "Reconnect"} and self.worker is None:
                self._resume_task = asyncio.create_task(self.update(self._last_update))

    def _publish(self):
        snapshot = self.latest_snapshot
        round_start = snapshot.get("fields", {}).get("round_start", {}) if snapshot else {}
        fresh_start = False
        if round_start.get("value") is True and round_start.get("read_at"):
            fresh_start = 0 <= (datetime.now(UTC) - datetime.fromisoformat(round_start["read_at"])).total_seconds() <= 2
        faced = []
        if snapshot:
            for row in snapshot.get("fields", {}).get("recent_opponent_fights", {}).get("value", []):
                faced.append({"name": row["opponent_id"], "result": row["result"]})
        self.server.publish_baseline(data=self.pinned_data if self.latest_snapshot else None,
            snapshot=snapshot, status=self.status, round_start=fresh_start, faced=faced)

    def _failure(self, message):
        self.status = message
        self.latest_snapshot = None
        self._publish()

    def _receive_snapshot(self, snapshot):
        # One scheduled drain plus one replaceable frame, even if Baseline is
        # busy. A thread cannot accumulate a callback for every captured frame.
        with self._incoming_lock:
            self._incoming = snapshot
            if self._incoming_scheduled:
                return
            self._incoming_scheduled = True
        self._marshal(self._drain_snapshot, None)

    def _drain_snapshot(self, unused):
        with self._incoming_lock:
            snapshot = self._incoming
            self._incoming = None
            self._incoming_scheduled = False
        if snapshot:
            self._snapshot(snapshot)

    def _clear_handoff(self):
        while not self._handoff.empty():
            self._handoff.get_nowait()

    def _snapshot(self, snapshot):
        if self._closed or snapshot.get("game_id") != self.sessions.active_game_id:
            return
        self.latest_snapshot = snapshot
        self.status = "Capture active" + ("; " + "; ".join(self.pinned_data.warnings) if self.pinned_data.warnings else "")
        if self._handoff.full():
            self._handoff.get_nowait()
        self._handoff.put_nowait(snapshot)
        self._publish()

    async def next_snapshot(self):
        """Bounded latest-value handoff; ticket 45 decides permitted Engine dispatch."""
        return await self._handoff.get()

    async def update(self, update):
        async with self._lock:
            if self._closed:
                return
            self._loop = asyncio.get_running_loop()
            self._last_update = update
            try:
                if update.phase in {"InProgress", "Reconnect"}:
                    if not update.game_id or update.game_mode != "TFT":
                        self.status = "Capture unavailable: LCU has no positively identified TFT game"
                    elif self.sessions.active_game_id not in {None, update.game_id}:
                        self.status = "Capture unavailable: previous game outcome is unknown; retain its log for recovery"
                    elif self.worker is None:
                        self._begin(update.game_id)
                elif update.phase in {"EndOfGame", "WaitingForStats"} and self.sessions.active_game_id:
                    if update.game_id == self.sessions.active_game_id and update.game_mode == "TFT":
                        if await self._stop_worker():
                            game_id, mode = self.sessions.active_game_id, self.sessions.mode.value
                            self.sessions.end_game()
                            stored = next(game for game in self.sessions.list_games() if game["game_id"] == game_id)
                            self.completed_game = {**stored, "final_mode": mode}
                            self.latest_snapshot = None
                            self._clear_handoff()
                            self.pinned_data = None
                            if self.refresh:
                                self.refresh.set_in_game(False)
                            self._trigger_refresh("end-of-game")
                    else:
                        self.status = "Terminal game identity unavailable; outcome remains unconfirmed"
                elif not update.client_running or update.phase in {None, "None", "Lobby"}:
                    if self.sessions.active_game_id:
                        if self.worker:
                            await self._stop_worker()
                            self.sessions.append_event("capture_gap", {"reason": "client_or_game_identity_lost", "start": None, "end": datetime.now(UTC).isoformat()})
                        self.status = "Capture paused: game outcome unknown; log retained for reattachment"
                        self.latest_snapshot = None
                        self._clear_handoff()
                    elif update.phase == "Lobby":
                        self._trigger_refresh("Lobby")
            except Exception as error:
                if self.refresh and self.sessions.active_game_id is None:
                    self.refresh.set_in_game(False)
                self.status = f"Session lifecycle unavailable: {type(error).__name__}: {error}"
                log.exception("Session lifecycle failed; watcher remains available")
            self.server.publish_gameflow(update)
            self._publish()

    def _begin(self, game_id):
        if not self.settings:
            return
        events = self.sessions.read_events(game_id)
        original = events[0]["payload"] if events else None
        data = self.data_store.get(original["data_snapshot_id"]) if original and original.get("data_snapshot_id") else self.data_store.current
        if data is None:
            raise ValueError("No validated immutable data snapshot; prepare and qualify data before capture")
        if original and not original.get("data_snapshot_id"):
            raise ValueError("Existing game has no original data pin; capture cannot invent one")
        if self.refresh:
            self.refresh.set_in_game(True)
        pointer = json.loads(self.settings.model_pointer.read_text())
        if not isinstance(pointer.get("version"), str) or not pointer["version"].strip():
            raise ValueError("Reviewed model pointer has no version")
        self.sessions.start_game(game_id, patch=data.patch, data_snapshot_id=data.snapshot_id,
            model_version=pointer["version"], previous_patch=data.patch != self.settings.expected_patch,
            engine_version=self._engine_version, set_id=str(data.set_number))
        original = self.sessions.read_events(game_id)[0]["payload"]
        self.pinned_data = data
        self.worker = _CaptureWorker(self.settings, data, self.sessions, self.devices,
            self._receive_snapshot,
            lambda error: self._marshal(self._failure, error), original=original)
        self.worker.thread.start()

    def _marshal(self, callback, value):
        try:
            if self._loop and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(callback, value)
        except RuntimeError:
            log.error("Capture callback arrived after event loop shutdown")

    async def _stop_worker(self):
        worker = self.worker
        if not worker:
            return True
        # Native stop may itself block. Keep it on the existing capture thread's
        # separate control thread and make timeout observable instead of freezing LCU.
        threading.Thread(target=worker.stop, name="tft-capture-stop", daemon=True).start()
        deadline = asyncio.get_running_loop().time() + self.shutdown_seconds
        while not worker.done.is_set() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(.01)
        if not worker.done.is_set():
            self.status = "Capture shutdown timed out; media may be incomplete; active log remains recoverable"
            self.sessions.append_event("capture_shutdown_timeout", {"seconds": self.shutdown_seconds, "media_complete": False})
            return False
        worker.thread.join(timeout=0)
        self.worker = None
        if worker.error:
            self.status = worker.error
        return True

    async def shutdown(self):
        async with self._lock:
            self._closed = True
            if self._resume_task and not self._resume_task.done():
                self._resume_task.cancel()
                await asyncio.gather(self._resume_task, return_exceptions=True)
            await self._stop_worker()
            if self.refresh and self.refresh.task and not self.refresh.task.done():
                self.refresh.set_in_game(True)
                self.refresh.task.cancel()
                await asyncio.gather(self.refresh.task, return_exceptions=True)
                self.status = "Data refresh interrupted by shutdown; last-good publication retained"
                log.warning("%s", self.status)
            self.latest_snapshot = None
            self._handoff.shutdown(immediate=True)
            self._publish()
