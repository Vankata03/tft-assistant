"""Bounded background video encoding with explicit frame times and durable segments.

FFmpeg's concat demuxer carries variable frame durations; completed MP4 files
are handed to SessionStore. Capture must close this recorder before ending the
active game, so the final segment can still be indexed in that game's log.
"""

from datetime import datetime
from pathlib import Path
from queue import Queue, Full, Empty
import shutil
import subprocess
import tempfile
import threading
import time
import math


class SegmentRecorder:
    def __init__(
        self,
        sink,
        *,
        executable=None,
        segment_seconds=5,
        queue_size=16,
        close_timeout=30,
    ):
        self.sink = sink
        self.executable = executable or shutil.which("ffmpeg")
        if not self.executable:
            raise ValueError("Full video requires a configured FFmpeg executable")
        if segment_seconds <= 0 or queue_size < 1:
            raise ValueError(
                "Video segment duration and queue capacity must be positive"
            )
        if not math.isfinite(close_timeout) or close_timeout <= 0:
            raise ValueError("Video close timeout must be positive and finite")
        self.close_timeout = close_timeout
        self._abort = threading.Event()
        self._process_lock = threading.Lock()
        self._process = None
        self.segment_seconds = segment_seconds
        self.queue = Queue(queue_size)
        self.closed = False
        self.error = None
        self.worker = threading.Thread(
            target=self._run, name="tft-video-encoder", daemon=True
        )
        self.worker.start()

    def submit(self, image, timestamp):
        if self.closed:
            raise ValueError("Video recorder is closed")
        if self.error:
            raise RuntimeError(self.error)
        try:
            self.queue.put_nowait(("frame", image.copy(), timestamp))
        except Full:
            self.sink.append_event(
                "video_gap",
                {"reason": "encoder_queue_full"},
                timestamp=timestamp.isoformat(),
            )

    def flush(self):
        if not self.closed:
            try:
                self.queue.put_nowait(("flush", None, None))
            except Full:
                self.sink.append_event(
                    "video_gap", {"reason": "encoder_flush_queue_full"}
                )

    def close(self):
        if self.closed:
            return
        self.closed = True
        deadline = time.monotonic() + self.close_timeout
        try:
            self.queue.put(("close", None, None), timeout=self.close_timeout)
            self.worker.join(timeout=max(0, deadline - time.monotonic()))
        except Full:
            pass  # The deadline path below records incomplete media explicitly.
        if self.worker.is_alive():
            self.error = "Video finalization timed out; media is incomplete"
            self._abort.set()
            self.sink.append_event(
                "video_gap",
                {"reason": "encoder_shutdown_timeout", "media_complete": False},
            )
            self.sink.append_event(
                "media_status", {"state": "unavailable", "error": self.error}
            )
            with self._process_lock:
                if self._process and self._process.poll() is None:
                    process = self._process
                    process.terminate()
                    try:
                        process.wait(timeout=0.25)
                    except subprocess.TimeoutExpired:
                        # Only our encoder is killed, after a durable media-gap
                        # report. A stubborn encoder cannot survive core teardown.
                        process.kill()
                        process.wait(timeout=0.25)
            self.worker.join(timeout=0.5)
            if self.worker.is_alive():
                raise RuntimeError(self.error + "; encoder worker remains unavailable")
        if self.error:
            raise RuntimeError(self.error)

    def _run(self):
        frames = []
        with tempfile.TemporaryDirectory(prefix="tft-video-") as directory:
            root = Path(directory)
            while not self._abort.is_set():
                try:
                    kind, image, timestamp = self.queue.get(timeout=0.1)
                except Empty:
                    continue
                try:
                    if kind == "frame":
                        if frames and (
                            image.size != frames[0][2]
                            or (timestamp - frames[0][0]).total_seconds()
                            >= self.segment_seconds
                        ):
                            self._encode(root, frames)
                            frames = []
                        path = root / f"{len(frames)}.png"
                        image.convert("RGB").save(path)
                        frames.append((timestamp, path, image.size))
                    else:
                        if frames:
                            self._encode(root, frames)
                            frames = []
                        if kind == "close":
                            return
                except (
                    OSError,
                    ValueError,
                    RuntimeError,
                    subprocess.SubprocessError,
                ) as error:
                    self.error = self.error or f"Video encoding failed: {error}"
                    frames = []
                    self.sink.append_event(
                        "media_status",
                        {"state": "unavailable", "error": self.error},
                        timestamp=timestamp.isoformat() if timestamp else None,
                    )
                    if kind == "close":
                        return
                finally:
                    self.queue.task_done()

    def _encode(self, root, frames):
        # Relative numeric filenames avoid shell quoting and concat path injection.
        lines = []
        for index, (timestamp, path, _) in enumerate(frames):
            duration = (
                (frames[index + 1][0] - timestamp).total_seconds()
                if index + 1 < len(frames)
                else 0.25
            )
            if duration <= 0:
                raise ValueError("Video frame timestamps must increase")
            lines.extend((f"file '{path.name}'", f"duration {duration:.9f}"))
        lines.append(f"file '{frames[-1][1].name}'")
        manifest = root / "frames.txt"
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        output = root / "segment.mp4"
        executable = (
            [self.executable]
            if isinstance(self.executable, (str, Path))
            else list(self.executable)
        )
        command = [
            *executable,
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            str(manifest),
            "-fps_mode",
            "vfr",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
        with self._process_lock:
            if self._abort.is_set():
                raise RuntimeError("Media is incomplete after encoder shutdown")
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            self._process = process
        try:
            try:
                _, stderr = process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise RuntimeError(
                    "Video encoder exceeded its 30 second segment deadline"
                ) from None
        finally:
            with self._process_lock:
                self._process = None
        if self._abort.is_set():
            raise RuntimeError("Media is incomplete after encoder shutdown")
        if process.returncode:
            raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())
        path = self.sink.write_video(
            output.read_bytes(), timestamp=frames[0][0].isoformat()
        )
        self.sink.append_event(
            "video_segment",
            {
                "path": path,
                "start": frames[0][0].isoformat(),
                "end": frames[-1][0].isoformat(),
                "frame_timestamps": [frame[0].isoformat() for frame in frames],
            },
            timestamp=frames[0][0].isoformat(),
        )
