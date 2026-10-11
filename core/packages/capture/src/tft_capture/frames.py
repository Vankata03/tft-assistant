"""Owned native BGRA frames with lazy, cached RGB region copies.

The capture API has already produced a native window surface. Polling does not
convert or copy that whole surface to RGB. OCR copies requested rectangles;
board recognition borrows a BGR view; keyframes/video materialize RGB once.
"""
from PIL import Image


class RegionFrame:
    def __init__(self, buffer, *, owner=None):
        import numpy as np
        array = np.asarray(buffer)
        if array.dtype != np.uint8 or array.ndim != 3 or array.shape[2] not in (3, 4) or min(array.shape[:2]) <= 0:
            raise ValueError('Capture needs a nonempty uint8 BGR/BGRA surface')
        self._buffer, self._owner = array, owner
        self.height, self.width = array.shape[:2]
        self.size = self.width, self.height
        self._crops = {}
        self._full = None
        self.copy_stats = {'region_rgb_bytes': 0, 'full_rgb_bytes': 0, 'region_rgb_copies': 0, 'full_rgb_copies': 0}

    def bgr_view(self):
        view = self._buffer[:, :, :3].view()
        view.setflags(write=False)
        return view

    def crop(self, rectangle):
        rectangle = tuple(rectangle)
        if rectangle not in self._crops:
            x0, y0, x1, y1 = rectangle
            if not (0 <= x0 < x1 <= self.width and 0 <= y0 < y1 <= self.height):
                raise ValueError('Capture crop must stay within the client surface')
            image = Image.fromarray(self._buffer[y0:y1, x0:x1, 2::-1])
            self._crops[rectangle] = image
            self.copy_stats['region_rgb_bytes'] += image.width*image.height*3
            self.copy_stats['region_rgb_copies'] += 1
        return self._crops[rectangle]

    def materialize(self):
        if self._full is None:
            self._full = Image.fromarray(self._buffer[:, :, 2::-1])
            self.copy_stats['full_rgb_bytes'] += self.width*self.height*3
            self.copy_stats['full_rgb_copies'] += 1
        return self._full

    def convert(self, mode):
        return self.materialize().convert(mode)


def full_image(frame):
    return frame.materialize() if isinstance(frame, RegionFrame) else frame
