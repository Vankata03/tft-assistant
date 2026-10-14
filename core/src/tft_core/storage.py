"""Durable session state and the append-only game-log boundary.

Logs and run.json are authoritative. SQLite is a disposable projection. Every
acknowledged event is flushed to disk before the caller may render advice or
capture the next snapshot. Only an incomplete final record may be discarded.
"""

import importlib.util
import errno
import json
import os
import re
import sqlite3
import threading
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from weakref import WeakValueDictionary
from time import monotonic, sleep

from tft_core.messages import SessionMode

_MODE_RANK = {SessionMode.SILENT: 0, SessionMode.BASELINE: 1, SessionMode.LIVE: 2}
_STORE_LOCKS = WeakValueDictionary()
_STORE_LOCKS_GUARD = threading.Lock()
# Application I/O policy, not a game rule. A busy store must fail visibly so
# startup/shutdown can reconcile a child rather than wait on it indefinitely.
_STORE_LOCK_TIMEOUT_SECONDS = 1.0


class _StoreLock:
    """Reentrant thread exclusion and one OS lock shared by all store processes."""

    def __init__(self, root: Path) -> None:
        self.path = root / ".session-store.lock"
        self.thread_lock = threading.RLock()
        self.depth = 0
        self.stream = None

    def __enter__(self):
        deadline = monotonic() + _STORE_LOCK_TIMEOUT_SECONDS
        if not self.thread_lock.acquire(timeout=_STORE_LOCK_TIMEOUT_SECONDS):
            raise TimeoutError("Session store is busy; retry when its writer finishes")
        try:
            if self.depth == 0:
                self.stream = self.path.open("a+b")
                while True:
                    try:
                        if os.name == "nt":
                            import msvcrt
                            self.stream.seek(0)
                            msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError as error:
                        if error.errno not in (errno.EACCES, errno.EAGAIN):
                            raise
                        remaining = deadline - monotonic()
                        if remaining <= 0:
                            raise TimeoutError("Session store is busy; retry when its writer finishes") from error
                        sleep(min(.01, remaining))
            self.depth += 1
            return self
        except BaseException:
            if self.depth == 0 and self.stream is not None:
                self.stream.close()
                self.stream = None
            self.thread_lock.release()
            raise

    def __exit__(self, *error):
        self.depth -= 1
        try:
            if self.depth == 0:
                try:
                    if os.name == "nt":
                        import msvcrt
                        self.stream.seek(0)
                        msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
                finally:
                    self.stream.close()
                    self.stream = None
        finally:
            self.thread_lock.release()


def _store_lock(root: Path) -> _StoreLock:
    # Separate SessionStore objects in one process share the reentrant lock.
    # Keep the on-disk lock file: unlinking it could split live lock holders.
    root = root.resolve()
    with _STORE_LOCKS_GUARD:
        lock = _STORE_LOCKS.get(root)
        if lock is None:
            lock = _StoreLock(root)
            _STORE_LOCKS[root] = lock
        return lock


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(value, output, allow_nan=False)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def _game_id(value: str | int) -> str:
    value = str(value)
    if not re.fullmatch(r"[0-9]+", value) or int(value) <= 0:
        raise ValueError("game_id must be the positive numeric League client game id")
    return value


def _observation_hash(events: list[dict]) -> str:
    import hashlib
    observations = [event for event in events if event["kind"] != "replay_cache"]
    return hashlib.sha256(json.dumps(observations, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class SessionStore:
    """Capture writes events; replay, review and the harness consume them."""

    def __init__(self, root: Path, config_root: Path, *, live_installed: bool | None = None) -> None:
        self.root, self.config_root = Path(root), Path(config_root)
        self.logs = self.root / "games"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.config_root.mkdir(parents=True, exist_ok=True)
        self.live_installed = importlib.util.find_spec("tft_live") is not None if live_installed is None else live_installed
        self._lock = _store_lock(self.root)
        self._next_seq: dict[str, int] = {}
        self._tag_locks: dict[str, threading.Lock] = {}
        self._log_sizes: dict[str, int] = {}
        self.active_game_id: str | None = None
        self._mode = self.default_mode
        settings = self.config_root / "session.json"
        if settings.exists():
            self._mode = SessionMode(json.loads(settings.read_text())["mode"])
        if not self.live_installed and self._mode is SessionMode.LIVE:
            self._mode = SessionMode.BASELINE
        self.rebuild_index()

    @classmethod
    def default_locations(cls) -> tuple[Path, Path]:
        """Resolve operator locations without opening or rebuilding the store."""
        home = Path.home()
        default_root = Path(os.environ.get("LOCALAPPDATA", home / ".local" / "share")) / "tft-assistant"
        root = Path(os.environ.get("TFT_ASSISTANT_DATA_ROOT", default_root))
        config_root = Path(os.environ.get("TFT_ASSISTANT_CONFIG_ROOT", home / ".config" / "tft-assistant"))
        return root, config_root

    @classmethod
    def default(cls) -> "SessionStore":
        return cls(*cls.default_locations())

    @property
    def run(self) -> dict | None:
        path = self.config_root / "run.json"
        return json.loads(path.read_text()) if path.exists() else None

    @property
    def default_mode(self) -> SessionMode:
        if not self.live_installed:
            return SessionMode.BASELINE
        return SessionMode.LIVE if self.run else SessionMode.SILENT

    @property
    def mode(self) -> SessionMode:
        return self._mode

    def log_path(self, game_id: str | int) -> Path:
        return self.logs / _game_id(game_id) / "events.jsonl"

    def read_events(self, game_id: str | int) -> list[dict]:
        """Read committed records in sequence, ignoring only a torn final line."""
        path = self.log_path(game_id)
        if not path.exists():
            return []
        events = []
        for line in path.read_bytes().splitlines(keepends=True):
            if not line.endswith(b"\n"):
                break
            try:
                event = json.loads(line)
            except (ValueError, UnicodeDecodeError) as error:
                raise ValueError(f"corrupt committed game log: {path}") from error
            if not isinstance(event, dict) or event.get("seq") != len(events):
                raise ValueError(f"invalid event sequence: {path}")
            events.append(event)
        return events

    def _append(self, game_id: str, kind: str, payload: dict, timestamp: str | None = None) -> dict:
        path = self.log_path(game_id)
        size = path.stat().st_size if path.exists() else 0
        # A background process may have appended cache evidence since this
        # instance last wrote. Reuse the fast path only for unchanged bytes.
        if game_id not in self._next_seq or self._log_sizes.get(game_id) != size:
            self._next_seq[game_id] = len(self.read_events(game_id))
        sequence = self._next_seq[game_id]
        event = {"v": 1, "seq": sequence, "kind": kind, "timestamp": timestamp or utc_now(), "payload": payload}
        encoded = (json.dumps(event, allow_nan=False, separators=(",", ":")) + "\n").encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        self._next_seq[game_id] = sequence + 1
        self._log_sizes[game_id] = size + len(encoded)
        return event

    def append_event(self, kind: str, payload: dict, *, timestamp: str | None = None, expected_game_id=None, expected_mode=None) -> dict:
        with self._lock:
            if self.active_game_id is None:
                raise ValueError("no active game")
            if kind in {"game_start", "mode_change", "game_end", "session_detached"}:
                raise ValueError("session events must use the session lifecycle API")
            if expected_game_id is not None and self.active_game_id != str(expected_game_id):
                raise ValueError("event game was superseded")
            if expected_mode is not None and self.mode != SessionMode(expected_mode):
                raise ValueError("event mode permission changed")
            return self._append(self.active_game_id, kind, payload, timestamp)

    def start_game(self, game_id: str | int, *, patch: str | None = None, data_snapshot_id: str | None = None,
                   model_version: str | None = None, previous_patch: bool = False, engine_version: str = "",
                   set_id: str | None = None, timestamp: str | None = None) -> None:
        with self._lock:
            game_id = _game_id(game_id)
            if self.active_game_id == game_id:
                return
            if self.active_game_id is not None:
                raise ValueError("another game is active")
            events = self.read_events(game_id)
            if events and any(event["kind"] == "game_end" for event in events):
                raise ValueError("game is already finished")
            path = self.log_path(game_id)
            raw = path.read_bytes() if path.exists() else b""
            committed_size = raw.rfind(b"\n") + 1
            torn_tail = committed_size != len(raw)
            if torn_tail:
                with path.open("r+b") as output:
                    output.truncate(committed_size)
                    output.flush()
                    os.fsync(output.fileno())
            self.active_game_id = game_id
            if events:
                self._mode = SessionMode(events[0]["payload"]["mode"])
                for event in events:
                    if event["kind"] == "mode_change":
                        self._mode = SessionMode(event["payload"]["mode"])
                self._append(game_id, "capture_gap", {"reason": "core_restart", "start": events[-1]["timestamp"],
                                                     "end": timestamp or utc_now()}, timestamp)
                if not self.live_installed and self._mode is SessionMode.LIVE:
                    self.set_mode(SessionMode.BASELINE)
            else:
                self._append(game_id, "game_start", {"game_id": game_id, "mode": self.mode.value, "patch": patch,
                    "data_snapshot_id": data_snapshot_id, "model_version": model_version,
                    "previous_patch": previous_patch, "engine_version": engine_version, "set_id": str(set_id) if set_id is not None else None}, timestamp)
                if torn_tail:
                    self._append(game_id, "capture_gap", {"reason": "incomplete_first_event", "start": None,
                                                         "end": timestamp or utc_now()}, timestamp)
            self.rebuild_index()

    def set_mode(self, mode: SessionMode | str) -> None:
        with self._lock:
            mode = SessionMode(mode)
            if mode is SessionMode.LIVE and not self.live_installed:
                raise ValueError("Live advisor is not installed")
            if self.active_game_id and _MODE_RANK[mode] > _MODE_RANK[self.mode]:
                raise ValueError("during a game the mode can only downgrade")
            if mode == self.mode:
                return
            if self.active_game_id:
                self._append(self.active_game_id, "mode_change", {"mode": mode.value})
            _atomic_json(self.config_root / "session.json", {"mode": mode.value})
            self._mode = mode
            self.rebuild_index()

    def detach_game(self, game_id: str | int, *, reason: str, timestamp: str | None = None) -> None:
        """Release ownership without declaring an outcome; caller must stop all writers first."""
        with self._lock:
            game_id = _game_id(game_id)
            if self.active_game_id != game_id:
                raise ValueError("detach requires the expected active game")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("detach requires an explicit recovery reason")
            self._append(game_id, "session_detached", {"reason": reason}, timestamp)
            next_mode = self.default_mode
            _atomic_json(self.config_root / "session.json", {"mode": next_mode.value})
            self.active_game_id = None
            self._mode = next_mode
            self.rebuild_index()

    def end_game(self, *, placement: int | None = None, timestamp: str | None = None) -> None:
        with self._lock:
            if self.active_game_id is None:
                return
            if placement is not None and not 1 <= placement <= 8:
                raise ValueError("placement must be 1 through 8")
            self._append(self.active_game_id, "game_end", {"placement": placement}, timestamp)
            self.active_game_id = None
            self._mode = self.default_mode
            _atomic_json(self.config_root / "session.json", {"mode": self._mode.value})
            self.enforce_media_cap()

    def rebuild_index(self) -> None:
        """Recreate the disposable index only from logs and the frozen run."""
        with self._lock:
            games = []
            replay_entries = []
            run = self.run
            for path in self.logs.glob("*/events.jsonl"):
                events = self.read_events(path.parent.name)
                if not events:
                    continue
                start = events[0]
                if start["kind"] != "game_start":
                    raise ValueError(f"game log has no start: {path}")
                replay_entries.extend((path.parent.name, json.dumps(e["payload"])) for e in events if e["kind"] == "replay_cache")
                metadata = start["payload"]
                modes = [SessionMode(metadata["mode"])] + [SessionMode(e["payload"]["mode"]) for e in events if e["kind"] == "mode_change"]
                highest = max(modes, key=_MODE_RANK.__getitem__)
                end = next((e for e in reversed(events) if e["kind"] == "game_end"), None)
                games.append({"game_id": path.parent.name, "date": start["timestamp"], "patch": metadata.get("patch"),
                    "set_id": metadata.get("set_id"), "placement": end["payload"].get("placement") if end else None,
                    "mode": highest.value, "review_locked": highest is SessionMode.SILENT and run is None,
                    "pinned": False, "block": None, "run_number": None, "engine_version": metadata.get("engine_version", ""),
                    "data_snapshot_id": metadata.get("data_snapshot_id"), "finished": end is not None})
            games.sort(key=lambda g: (g["date"], int(g["game_id"])))
            number = 0
            for game in games:
                if (run and game["mode"] == "live" and
                    datetime.fromisoformat(game["date"].replace("Z", "+00:00")) >= datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
                    and game["set_id"] == run["set_id"] and number < 50):
                    game["pinned"] = True
                    if game["finished"]:
                        number += 1
                        game.update(block=(number - 1) // 10 + 1, run_number=number)
            descriptor, name = tempfile.mkstemp(prefix="index.rebuild-", suffix=".sqlite3", dir=self.root)
            os.close(descriptor)
            temporary = Path(name)
            try:
                with closing(sqlite3.connect(temporary)) as connection:
                    connection.execute("CREATE TABLE games (game_id TEXT PRIMARY KEY, record TEXT NOT NULL)")
                    connection.execute("CREATE TABLE replay_cache (game_id TEXT NOT NULL, record TEXT NOT NULL)")
                    connection.executemany("INSERT INTO replay_cache VALUES (?, ?)", replay_entries)
                    connection.executemany("INSERT INTO games VALUES (?, ?)", [(g["game_id"], json.dumps(g)) for g in games])
                    connection.commit()
                os.replace(temporary, self.root / "index.sqlite3")
            finally:
                temporary.unlink(missing_ok=True)

    def list_games(self) -> list[dict]:
        with self._lock, closing(sqlite3.connect(self.root / "index.sqlite3")) as connection:
            return [json.loads(row[0]) for row in connection.execute("SELECT record FROM games ORDER BY game_id")]

    def start_run(self, baseline: dict, *, set_id: str, timestamp: str | None = None) -> dict:
        """Freeze the API-refreshed 50-game baseline; there is no review override."""
        with self._lock:
            if self.run:
                raise ValueError("Live-mode run already started")
            if self.active_game_id:
                raise ValueError("cannot start a run during a game")
            if not self.live_installed:
                raise ValueError("Live advisor is not installed")
            from tft_harness.baseline import validate_baseline
            baseline = validate_baseline(baseline, set_id=set_id, logged_games=self.list_games())
            started_at = timestamp or utc_now()
            if datetime.fromisoformat(baseline["refreshed_at"]) > datetime.fromisoformat(started_at.replace("Z", "+00:00")):
                raise ValueError("baseline refresh must precede run start")
            run = {"v": 1, "started_at": started_at, "set_id": str(set_id), "baseline": baseline}
            _atomic_json(self.config_root / "run.json", run)
            self._mode = self.default_mode
            _atomic_json(self.config_root / "session.json", {"mode": self._mode.value})
            self.rebuild_index()
            return run

    def write_keyframe(self, image, *, reason: str, timestamp: str | None = None) -> str:
        """Persist a lossless RGB/RGBA WebP and reference it in the game log."""
        from io import BytesIO
        from PIL import Image

        if isinstance(image, bytes):
            image = Image.open(BytesIO(image))
        with self._lock:
            if self.active_game_id is None:
                raise ValueError("no active game")
            buffer = BytesIO()
            image.save(buffer, format="WEBP", lossless=True, exact=True)
            return self._write_media(buffer.getvalue(), suffix="webp", kind="keyframe", reason=reason, timestamp=timestamp)

    def write_video(self, content: bytes, *, timestamp: str | None = None) -> str:
        """Persist a completed recorder segment; video encoding is capture-owned."""
        with self._lock:
            return self._write_media(content, suffix="mp4", kind="video", reason="full_video", timestamp=timestamp)

    def _write_media(self, content: bytes, *, suffix: str, kind: str, reason: str, timestamp: str | None) -> str:
        if self.active_game_id is None:
            raise ValueError("no active game")
        import uuid

        name = f"media/{uuid.uuid4().hex}.{suffix}"
        path = self.log_path(self.active_game_id).parent / name
        path.parent.mkdir(exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        self._append(self.active_game_id, kind, {"path": name, "reason": reason, "bytes": len(content)}, timestamp)
        self.enforce_media_cap()
        return name

    def read_media(self, game_id: str | int, name: str) -> bytes | None:
        directory = self.log_path(game_id).parent
        path = (directory / name).resolve()
        if not path.is_relative_to((directory / "media").resolve()):
            raise ValueError("media path must stay within its game's media directory")
        return path.read_bytes() if path.is_file() else None

    def write_evidence(self, graph, *, expected_game_id=None, expected_mode=None, cancelled=None) -> dict:
        """Persist outside the session lock; publish only under current permissions.

        The immutable graph file is encoded and flushed before acquiring the
        short log-publication lock. A mode change or finished/different game
        removes the temporary file and cannot publish a reference into its log.
        """
        from hashlib import sha256
        from uuid import uuid4
        from tft_engine.evidence import canonical_bytes

        def permitted(game_id):
            if cancelled and cancelled():raise ValueError('evidence publication was cancelled')
            if self.active_game_id != game_id or game_id is None:
                raise ValueError("evidence game was superseded")
            if expected_mode is not None and self.mode != SessionMode(expected_mode):
                raise ValueError("evidence mode permission changed")
        with self._lock:
            game_id = str(expected_game_id) if expected_game_id is not None else self.active_game_id
            permitted(game_id)
            name = graph.root_id.removeprefix("sha256:")
            if not re.fullmatch(r"[0-9a-f]{64}", name):
                raise ValueError("invalid evidence identity")
            path = self.log_path(game_id).parent / "evidence" / (name + ".json")
        content = canonical_bytes(graph.to_dict())
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{uuid4().hex}.tmp")
        try:
            existing = path.read_bytes() if path.exists() else None
            if existing is not None and canonical_bytes(json.loads(existing)) != content:
                raise ValueError("immutable evidence artifact was changed")
            if existing is None:
                with temporary.open("wb") as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
            with self._lock:
                permitted(game_id)
                if path.exists():
                    stored = path.read_bytes()
                    if stored != existing and canonical_bytes(json.loads(stored)) != content:
                        raise ValueError("immutable evidence artifact was changed")
                else:
                    os.replace(temporary,path)
                    stored = content
                reference = {"evidence_id": graph.root_id, "sha256": sha256(stored).hexdigest(), "bytes": len(stored)}
                self._append(game_id,"engine_evidence",reference)
                return reference
        finally:
            temporary.unlink(missing_ok=True)

    def read_evidence(self, game_id: str | int, evidence_id: str):
        """Raw offline access; UI/review callers must enforce their own access facade."""
        from hashlib import sha256
        from tft_engine.evidence import EvidenceGraph

        if not isinstance(evidence_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", evidence_id):
            raise ValueError("invalid evidence identity")
        references = [event["payload"] for event in self.read_events(game_id)
                      if event["kind"] == "engine_evidence" and event["payload"].get("evidence_id") == evidence_id]
        if not references:
            raise ValueError("evidence is not referenced by this game")
        path = self.log_path(game_id).parent / "evidence" / (evidence_id[7:] + ".json")
        content = path.read_bytes()
        if any(reference["sha256"] != sha256(content).hexdigest() or reference["bytes"] != len(content) for reference in references):
            raise ValueError("stored evidence bytes were changed")
        return EvidenceGraph.from_dict(json.loads(content))

    def enforce_media_cap(self, cap_bytes: int = 20 * 1024 ** 3) -> dict:
        """Delete oldest unpinned media, retaining structured logs forever."""
        if cap_bytes < 0:
            raise ValueError("media cap cannot be negative")
        with self._lock:
            self.rebuild_index()
            games = self.list_games()
            files = list(self.logs.glob("*/media/*"))
            total = sum(path.stat().st_size for path in files if path.is_file())
            deleted = []
            for game in sorted(games, key=lambda game: (game["date"], int(game["game_id"]))):
                if game["pinned"]:
                    continue
                for path in sorted((self.logs / game["game_id"] / "media").glob("*"), key=lambda p: p.stat().st_mtime):
                    if total <= cap_bytes:
                        break
                    if path.is_file():
                        total -= path.stat().st_size
                        path.unlink()
                        deleted.append(str(path.relative_to(self.logs)))
            return {"bytes": total, "deleted": deleted, "over_cap": total > cap_bytes}

    def write_replay_cache(self, game_id: str | int, records: list[dict], *, engine_version: str,
                           tunables_hash: str, data_snapshot_id: str, cache_identity: dict | None = None) -> None:
        """Store reusable replay output; dirty engine output is never reusable."""
        import hashlib

        game_id = _game_id(game_id)
        with self._lock:
            events = self.read_events(game_id)
            if not events:
                raise ValueError("replay requires a game log")
            if cache_identity is not None:
                observations = [event for event in events if event["kind"] != "replay_cache"]
                current_hash = _observation_hash(events)
                if (cache_identity.get("dirty") is not False or cache_identity.get("finished") is not True
                    or not any(event["kind"] == "game_end" for event in observations)
                    or current_hash != cache_identity.get("log_hash")):
                    raise ValueError("replay cache inputs changed or are not reusable")
            key = {"engine_version": engine_version, "tunables_hash": tunables_hash, "data_snapshot_id": data_snapshot_id}
            if cache_identity is not None:
                key["cache_identity"] = cache_identity
            digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
            relative = f"replay/{game_id}/{digest}.json"
            _atomic_json(self.root / relative, {"key": key, "records": records})
            content_hash = hashlib.sha256((self.root / relative).read_bytes()).hexdigest()
            self._append(game_id, "replay_cache", {**key, "path": relative, "content_hash": content_hash})
            self.rebuild_index()

    def read_replay_cache(self, game_id: str | int, *, engine_version: str, tunables_hash: str,
                          data_snapshot_id: str, cache_identity: dict | None = None) -> list[dict] | None:
        import hashlib
        if "dirty" in engine_version:
            return None
        key = {"engine_version": engine_version, "tunables_hash": tunables_hash, "data_snapshot_id": data_snapshot_id}
        if cache_identity is not None:
            key["cache_identity"] = cache_identity
        with self._lock, closing(sqlite3.connect(self.root / "index.sqlite3")) as connection:
            for (raw,) in connection.execute("SELECT record FROM replay_cache WHERE game_id = ?", (_game_id(game_id),)):
                entry = json.loads(raw)
                if all(entry.get(name) == value for name, value in key.items()):
                    path = (self.root / entry["path"]).resolve()
                    if not path.is_relative_to((self.root / "replay").resolve()):
                        raise ValueError("cache path escapes replay directory")
                    if path.exists():
                        content = path.read_bytes()
                        if entry.get("content_hash") and hashlib.sha256(content).hexdigest() != entry["content_hash"]:
                            raise ValueError("corrupt replay cache content")
                        if cache_identity is not None and not entry.get("content_hash"):
                            raise ValueError("replay cache lacks checked content identity")
                        cache = json.loads(content)
                        if cache["key"] == key:
                            return cache["records"]
            return None

    def write_review(self, game_id: str | int, review: dict, *, engine_version: str, data_snapshot_id: str,
                     expected_log_hash: str | None = None) -> None:
        game_id = _game_id(game_id)
        with self._lock:
            events = self.read_events(game_id)
            if not events:
                raise ValueError("review requires a game log")
            if expected_log_hash is not None and _observation_hash(events) != expected_log_hash:
                raise ValueError("review log evidence changed; regenerate before publication")
            _atomic_json(self.root / "reviews" / f"{game_id}.json", {"engine_version": engine_version,
                "data_snapshot_id": data_snapshot_id, "review": review,
                **({"log_hash": expected_log_hash} if expected_log_hash is not None else {})})

    def read_review(self, game_id: str | int) -> dict | None:
        game_id = _game_id(game_id)
        def permitted():
            game = next((g for g in self.list_games() if g['game_id']==game_id),None)
            if game is None:raise ValueError('review requires a game log')
            if game['review_locked']:raise PermissionError('silent-game review is locked until the Live-mode run starts')
        # Review files are replaced atomically. Heavy immutable reads do not
        # hold the capture/session lock or block a mode downgrade.
        permitted()
        path=self.root/'reviews'/f'{game_id}.json'
        if not path.exists():return None
        review=json.loads(path.read_text())
        tags_path=self.root/'reviews'/f'{game_id}.tags.json'
        tags=json.loads(tags_path.read_text()) if tags_path.exists() else {}
        with self._lock:
            permitted()
            if 'log_hash' in review and _observation_hash(self.read_events(game_id)) != review['log_hash']:
                raise ValueError('review log evidence changed; regeneration required')
        review['tags']=tags
        return review

    def set_review_tag(self, game_id: str | int, decision_id: str, tag: str) -> None:
        if tag not in {"agree", "disagree", "unsure"}:
            raise ValueError("tag must be agree, disagree or unsure")
        game_id = _game_id(game_id)
        with self._lock:
            tag_lock=self._tag_locks.setdefault(game_id,threading.Lock())
        # Separate tag serialization leaves capture and mode changes independent
        # of immutable report reads and the tag file's native flush.
        with tag_lock:
            report_path=self.root/"reviews"/f"{game_id}.json"
            before=report_path.stat()
            report_version=(before.st_ino,before.st_size,before.st_mtime_ns)
            stored = self.read_review(game_id)
            review = stored["review"] if stored else {}
            known = set(review.get("decision_ids", ()))
            for rows in (review.get("moments", ()), review.get("records", ()),
                         review.get("replay", {}).get("records", ())):
                known.update(row["decision_id"] for row in rows if "decision_id" in row)
            if decision_id not in known:
                raise ValueError("unknown review decision id")
            path = self.root / "reviews" / f"{game_id}.tags.json"
            original=path.stat() if path.exists() else None
            tag_version=(original.st_ino,original.st_size,original.st_mtime_ns) if original else None
            tags = json.loads(path.read_text()) if original else {}
            tags[decision_id] = tag
            from uuid import uuid4
            temporary=path.with_suffix(f".{uuid4().hex}.tmp")
            try:
                with temporary.open("w",encoding="utf-8") as output:
                    json.dump(tags,output,allow_nan=False)
                    output.flush()
                    os.fsync(output.fileno())
                with self._lock:
                    if self.active_game_id and self.mode is SessionMode.SILENT:
                        raise ValueError("Silent games suppress review surfaces")
                    game=next((row for row in self.list_games() if row['game_id']==game_id),None)
                    if not game or game['review_locked']:
                        raise PermissionError("silent-game review is locked")
                    current=report_path.stat()
                    current_tags=path.stat() if path.exists() else None
                    current_tag_version=(current_tags.st_ino,current_tags.st_size,current_tags.st_mtime_ns) if current_tags else None
                    if (current.st_ino,current.st_size,current.st_mtime_ns)!=report_version or current_tag_version!=tag_version:
                        raise ValueError("Review or tags changed; reload before retrying")
                    os.replace(temporary,path)
            finally:
                temporary.unlink(missing_ok=True)

    @property
    def media_mode(self) -> str:
        path = self.config_root / "media.json"
        return json.loads(path.read_text())["mode"] if path.exists() else "keyframes"

    def set_media_mode(self, mode: str) -> None:
        if mode not in {"keyframes", "full_video"}:
            raise ValueError("media mode must be keyframes or full_video")
        with self._lock:
            _atomic_json(self.config_root / "media.json", {"mode": mode})
