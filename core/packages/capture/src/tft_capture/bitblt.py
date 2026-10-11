"""Desktop BitBlt into an owned top-down BGRA DIB, without a full RGB copy.

The desktop transfer remains a native capture operation. Python borrows its
pixel surface until the frame is released and copies only requested regions.
No CAPTUREBLT flag is used; overlay exclusion still needs Windows evidence.
"""
import ctypes
from ctypes import wintypes

from tft_capture.frames import RegionFrame


class _BitmapOwner:
    def __init__(self, gdi, bitmap):
        self.gdi, self.bitmap = gdi, bitmap

    def __del__(self):
        if self.bitmap:
            self.gdi.DeleteObject(self.bitmap)
            self.bitmap = None


def capture_bitblt(bounds):
    import numpy as np

    user = ctypes.WinDLL('user32', use_last_error=True)
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    handle = wintypes.HANDLE
    user.GetDC.argtypes, user.GetDC.restype = [wintypes.HWND], handle
    user.ReleaseDC.argtypes, user.ReleaseDC.restype = [wintypes.HWND, handle], ctypes.c_int
    gdi.CreateCompatibleDC.argtypes, gdi.CreateCompatibleDC.restype = [handle], handle
    gdi.DeleteDC.argtypes, gdi.DeleteDC.restype = [handle], wintypes.BOOL
    gdi.SelectObject.argtypes, gdi.SelectObject.restype = [handle, handle], handle
    gdi.DeleteObject.argtypes, gdi.DeleteObject.restype = [handle], wintypes.BOOL
    gdi.BitBlt.argtypes = [handle, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        handle, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi.BitBlt.restype = wintypes.BOOL
    gdi.GdiFlush.argtypes, gdi.GdiFlush.restype = [], wintypes.BOOL

    class Header(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('width', wintypes.LONG), ('height', wintypes.LONG),
            ('planes', wintypes.WORD), ('bits', wintypes.WORD), ('compression', wintypes.DWORD),
            ('image_size', wintypes.DWORD), ('xppm', wintypes.LONG), ('yppm', wintypes.LONG),
            ('used', wintypes.DWORD), ('important', wintypes.DWORD)]
    class Info(ctypes.Structure):
        _fields_ = [('header', Header), ('color', wintypes.DWORD)]
    gdi.CreateDIBSection.argtypes = [handle, ctypes.POINTER(Info), wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p), handle, wintypes.DWORD]
    gdi.CreateDIBSection.restype = handle
    left, top, right, bottom = bounds
    width, height = right-left, bottom-top
    if width <= 0 or height <= 0:
        raise OSError('BitBlt client area is empty')
    desktop, compatible, bitmap, previous = user.GetDC(None), None, None, None
    retained = False
    try:
        if not desktop:
            raise OSError('GetDC failed for desktop capture')
        compatible = gdi.CreateCompatibleDC(desktop)
        if not compatible:
            raise OSError('CreateCompatibleDC failed')
        info = Info(Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, width*height*4, 0, 0, 0, 0), 0)
        pointer = ctypes.c_void_p()
        bitmap = gdi.CreateDIBSection(desktop, ctypes.byref(info), 0, ctypes.byref(pointer), None, 0)
        if not bitmap or not pointer.value:
            raise OSError('CreateDIBSection failed')
        previous = gdi.SelectObject(compatible, bitmap)
        if not previous or previous == ctypes.c_void_p(-1).value:
            previous = None
            raise OSError('SelectObject failed')
        if not gdi.BitBlt(compatible, 0, 0, width, height, desktop, left, top, 0x00CC0020):
            raise OSError('BitBlt failed')
        if not gdi.GdiFlush():
            raise OSError('GdiFlush failed before reading captured pixels')
        array = np.ctypeslib.as_array((ctypes.c_uint8*(width*height*4)).from_address(pointer.value)).reshape(height, width, 4)
        image = RegionFrame(array)
        image._owner = _BitmapOwner(gdi, bitmap)
        retained = True
        return image
    finally:
        if previous:
            gdi.SelectObject(compatible, previous)
        if compatible:
            gdi.DeleteDC(compatible)
        if desktop:
            user.ReleaseDC(None, desktop)
        if bitmap and not retained:
            gdi.DeleteObject(bitmap)
