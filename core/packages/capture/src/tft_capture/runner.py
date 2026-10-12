"""Drive the public capture boundary on its own CPU thread."""

import threading
import time
from datetime import datetime, timezone

from tft_capture.windows import CaptureUnavailable


class CaptureRunner:
    def __init__(self, source, pipeline):
        self.source, self.pipeline = source, pipeline
        self._last_window = None
        self._last_time = None
        self._gap = False
        self._status = None
        self._stopped = threading.Event()

    def step(self, *, timestamp: datetime | None = None) -> dict:
        now = timestamp or datetime.now(timezone.utc)
        try:
            captured = self.source.capture()
            status = {
                "state": "capturing",
                "source": captured.source,
                "window_id": captured.window_id,
            }
            if (
                self._last_window
                and captured.window_id != self._last_window
                and not self._gap
            ):
                self.pipeline.record_gap(
                    reason="window_replaced", start=self._last_time, end=now
                )
            self._last_window, self._last_time, self._gap = (
                captured.window_id,
                now,
                False,
            )
            frame = captured.image
        except CaptureUnavailable as error:
            status = {"state": "unavailable", "error": str(error)}
            frame = None
            self._gap = True
        if status != self._status:
            self.pipeline.sink.append_event(
                "capture_status", status, timestamp=now.isoformat()
            )
            self._status = status
        return self.pipeline.tick(frame, timestamp=now)

    @property
    def status(self):
        """Current transport status; consumers must not infer success from old fields."""
        return dict(
            self._status or {"state": "unavailable", "error": "Capture has not started"}
        )

    def run(self, on_snapshot=None):
        while not self._stopped.is_set():
            started = time.monotonic()
            snapshot = self.step()
            if on_snapshot:
                on_snapshot(snapshot)
            self._stopped.wait(
                max(
                    0,
                    getattr(self.pipeline, "poll_interval", 0.25)
                    - (time.monotonic() - started),
                )
            )

    def stop(self):
        self.request_stop()
        if hasattr(self.source, "close"):
            self.source.close()

    def request_stop(self):
        """Signal the loop without closing native resources on another thread."""
        self._stopped.set()
