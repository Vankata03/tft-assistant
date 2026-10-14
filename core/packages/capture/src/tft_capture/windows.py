"""Read the TFT window using WGC; rescan and use desktop BitBlt on failure.

No input or game-process memory API is used. Imports of Windows libraries are
lazy so log replay and fixture tests remain usable on other operating systems.
"""
import ctypes
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from tft_capture.frames import RegionFrame


class CaptureUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class CapturedFrame:
    image: object
    window_id: str
    source: str
    desktop_bounds: tuple[int, int, int, int] | None = None
    geometry_read_at: datetime | None = None

    def __post_init__(self):
        if self.desktop_bounds is None and self.geometry_read_at is None:
            return
        if (not isinstance(self.desktop_bounds, tuple) or len(self.desktop_bounds) != 4
            or any(type(value) is not int for value in self.desktop_bounds)
            or not isinstance(self.geometry_read_at, datetime) or self.geometry_read_at.tzinfo is None):
            raise ValueError("Captured desktop geometry requires physical bounds and an aware positive read")
        left, top, right, bottom = self.desktop_bounds
        if (right - left, bottom - top) != self.image.size:
            raise ValueError("Captured frame dimensions differ from its physical client bounds")

    def geometry(self):
        if self.desktop_bounds is None:
            return None
        left, top, right, bottom = self.desktop_bounds
        return {"window_id": self.window_id, "coordinate_space": "physical_pixels",
                "client_bounds": {"x": left, "y": top, "width": right-left, "height": bottom-top},
                "read_at": self.geometry_read_at.isoformat(), "source": "Win32-client-rectangle"}


class WindowsCaptureSource:
    """A polling boundary over the asynchronous Graphics Capture API."""
    def __init__(self, *, window_title: str = "TFT", allow_bitblt: bool = True):
        self.window_title = window_title
        self.allow_bitblt = allow_bitblt
        self._hwnd = None
        self._control = None
        self._frame = None
        self._frame_at = 0.0
        self._closed = False
        self._wgc_error = None
        self._retry_at = 0.0
        self._lock = threading.Lock()
        self._generation = 0

    def _window(self):
        from ctypes import wintypes
        user = ctypes.WinDLL("user32", use_last_error=True)
        # Capture runs on its own thread. Use physical client pixels at mixed DPI.
        user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user.IsWindowVisible.argtypes = [wintypes.HWND]
        user.IsIconic.argtypes = [wintypes.HWND]
        user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        matches = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        @callback_type
        def visit(hwnd, _):
            length = user.GetWindowTextLengthW(hwnd)
            text = ctypes.create_unicode_buffer(length + 1)
            user.GetWindowTextW(hwnd, text, length + 1)
            if text.value == self.window_title and user.IsWindowVisible(hwnd):
                matches.append(hwnd)
            return True
        user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        if not user.EnumWindows(visit, 0):
            raise CaptureUnavailable("Windows could not enumerate game windows")
        if len(matches) != 1:
            raise CaptureUnavailable("TFT window unavailable or ambiguous; rescanning on the next tick")
        hwnd = matches[0]
        rectangle, origin = wintypes.RECT(), wintypes.POINT(0, 0)
        if not user.GetClientRect(hwnd, ctypes.byref(rectangle)) or not user.ClientToScreen(hwnd, ctypes.byref(origin)):
            raise CaptureUnavailable("TFT client rectangle unavailable")
        if user.IsIconic(hwnd) or rectangle.right <= 0 or rectangle.bottom <= 0:
            raise CaptureUnavailable("TFT window is minimized or has no client area")
        return hwnd, (origin.x, origin.y, origin.x + rectangle.right, origin.y + rectangle.bottom)

    def _start_wgc(self, hwnd):
        generation = self._generation
        self._closed = False
        try:
            from windows_capture import WindowsCapture
            capture = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=hwnd,
                                     minimum_update_interval=66)
            self._closed = False
            @capture.event
            def on_frame_arrived(frame, capture_control):
                with self._lock:
                    if generation != self._generation:
                        return
                    # Keep the mapped frame's owned NumPy buffer alive until the poll.
                    self._frame = frame.frame_buffer
                    self._frame_at = time.monotonic()
            @capture.event
            def on_closed():
                if generation == self._generation:
                    self._closed = True
            self._control = capture.start_free_threaded()
            self._wgc_error = None
        except (ImportError, OSError, RuntimeError) as error:
            self._wgc_error = f"WGC unavailable: {error}"
            self._control = None
            self._retry_at = time.monotonic() + 5

    def capture(self) -> CapturedFrame:
        if sys.platform != "win32":
            raise CaptureUnavailable("Automatic capture requires Windows 11; replay and fixture workflows work on this platform")
        hwnd, bounds = self._window()
        geometry_read_at = datetime.now(UTC)
        if hwnd != self._hwnd:
            self.close()
            self._hwnd = hwnd
            self._retry_at = 0
        if self._control and (self._closed or self._control.is_finished()):
            self.close()
            self._hwnd = hwnd
        if self._control is None and time.monotonic() >= self._retry_at:
            self._start_wgc(hwnd)
        with self._lock:
            buffer = self._frame
            age = time.monotonic() - self._frame_at
        if buffer is not None and not self._closed and age <= 1:
            image = RegionFrame(buffer)
            target_size = (bounds[2]-bounds[0], bounds[3]-bounds[1])
            if image.size == target_size:
                return CapturedFrame(image, str(hwnd), "wgc", bounds, geometry_read_at)
            # A windowed WGC frame can contain the non-client border. Do not silently stretch it.
            self._wgc_error = "WGC frame differs from the client rectangle; use BitBlt and check calibration"
        if self.allow_bitblt:
            try:
                from tft_capture.bitblt import capture_bitblt
                image = capture_bitblt(bounds)
                return CapturedFrame(image, str(hwnd), "bitblt", bounds, geometry_read_at)
            except (OSError, RuntimeError) as error:
                raise CaptureUnavailable(f"WGC/BitBlt capture unavailable: {error}") from error
        raise CaptureUnavailable(self._wgc_error or "WGC has not supplied a fresh frame")

    def close(self) -> None:
        self._generation += 1
        if self._control:
            self._control.stop()
        self._control = None
        self._frame = None
        self._frame_at = 0.0
        self._hwnd = None
