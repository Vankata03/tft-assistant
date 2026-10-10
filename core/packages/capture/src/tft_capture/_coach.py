"""Adapted geometry and preprocessing from TFT-COACH.
Pinned upstream: bf22ac92010aef321b9e67d6f125bb2109c41cf4.
Source modules: board_crops.py, unit_classifier.py, unit_details.py, config.py.

MIT License

Copyright (c) 2026 mallangmallang0619

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# Keep upstream's explicit pixel integer casts for direct geometry comparison.
# ruff: noqa: RUF046
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class UnitCrop:
    zone: str
    position: int | None
    bounds: tuple[int, int, int, int]
    image: np.ndarray
    bar: tuple[int, int, int, int]


def viewport(size):
    width, height = size
    scale = min(width / 2560, height / 1440)
    return (width - 2560 * scale) / 2, (height - 1440 * scale) / 2, scale


def rectangle(size, fractions):
    x, y, scale = viewport(size)
    x0, y0, x1, y1 = fractions
    return tuple(
        round(value)
        for value in (
            x + x0 * 2560 * scale,
            y + y0 * 1440 * scale,
            x + x1 * 2560 * scale,
            y + y1 * 1440 * scale,
        )
    )


def hex_position(bar, size, *, foot_ratio=1.55):
    # Pinned perspective calibration; unknown projections remain unavailable.
    x0, y0, x1, y1 = rectangle(size, (0.25, 0.3819, 0.75, 0.6875))
    width, height = x1 - x0, y1 - y0
    row_y = (0.11136, 0.32500, 0.55227, 0.79318)
    pitch = (0.11862, 0.12279, 0.12695, 0.13281)
    centers = (0.44492, 0.44212, 0.44102, 0.43672)
    x, y, bw, _bh = bar
    foot_x, foot_y = x + bw / 2, y + bw * foot_ratio
    distances = []
    for row in range(4):
        for col in range(7):
            cx = (
                centers[row]
                + (col - 3) * pitch[row]
                + (pitch[row] / 2 if row % 2 else 0)
            )
            distance = ((foot_x - (x0 + cx * width)) / (width * 0.136)) ** 2 + (
                (foot_y - (y0 + row_y[row] * height)) / (height * 0.24)
            ) ** 2
            distances.append(distance)
    index = int(np.argmin(distances))
    return index if distances[index] <= 0.80 else None


def health_bars(frame, bounds):
    x0, y0, x1, y1 = bounds
    search = frame[y0:y1, x0:x1]
    if not search.size:
        return []
    height, width = frame.shape[:2]
    _, _, scale = viewport((width, height))
    hsv = cv2.cvtColor(search, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(
        hsv,
        np.array([45, 170, 50], dtype=np.uint8),
        np.array([75, 255, 255], dtype=np.uint8),
    )
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(3, round(2560 * scale / 300)), 1)
    )
    green = cv2.morphologyEx(green, cv2.MORPH_CLOSE, kernel)
    _, _, stats, _ = cv2.connectedComponentsWithStats(green)
    result = []
    for x, y, bw, bh, area in stats[1:]:
        if (
            max(24 * scale, 2560 * scale * 0.022) <= bw <= 2560 * scale * 0.045
            and max(2, 1440 * scale * 0.002) <= bh <= max(3, 1440 * scale * 0.014)
            and bw / max(1, bh) >= 4
            and area >= bw * bh * 0.30
        ):
            result.append((x0 + int(x), y0 + int(y), int(bw), int(bh)))
    return result


def crops(frame):
    height, width = frame.shape[:2]
    size = width, height
    _, _, scale = viewport(size)
    bx, by, br, bottom = rectangle(size, (0.25, 0.3819, 0.75, 0.6875))
    nx, ny, nr, nb = rectangle(size, (0.183, 0.6075, 0.748, 0.77))
    # Widen the pinned window upward; tall Maokai crops must survive before classification.
    board_bounds = (
        max(0, bx - round((br - bx) * 0.03)),
        max(0, by - round((bottom - by) * 0.85)),
        br,
        min(height, ny - max(2, round(height * 0.008))),
    )
    result = []
    for bar in health_bars(frame, board_bounds):
        x, y, bw, _bh = bar
        base = max(float(bw), 2560 * scale * 0.03)
        cw = round(base * 1.90)
        left = max(0, round(x + bw / 2 - cw / 2))
        right = min(width, left + cw)
        top = max(0, y - round(base * 0.42))
        lower = min(
            height,
            round(1440 * scale * 0.635 + viewport(size)[1]),
            y + round(base * 2.25),
        )
        if lower > top:
            result.append(
                UnitCrop(
                    "board",
                    hex_position(bar, size),
                    (left, top, right, lower),
                    frame[top:lower, left:right].copy(),
                    bar,
                )
            )
    # All nine slots are examined, including the animated portal-side slot.
    for slot in range(9):
        left = nx + round((nr - nx) * slot / 9)
        right = nx + round((nr - nx) * (slot + 1) / 9)
        inset = round((right - left) * 0.08)
        bounds = (left + inset, ny, right - inset, nb)
        bars = health_bars(frame, bounds)
        if bars:
            bar = max(bars, key=lambda item: item[2] * item[3])
            result.append(
                UnitCrop(
                    "bench",
                    slot,
                    bounds,
                    frame[ny:nb, left + inset : right - inset].copy(),
                    bar,
                )
            )
    return result


def preprocess(images, metadata):
    size = int(metadata["input_size"])
    mean = np.asarray(metadata["mean"], dtype=np.float32).reshape(3, 1, 1)
    std = np.asarray(metadata["std"], dtype=np.float32).reshape(3, 1, 1)
    batch = np.empty((len(images), 3, size, size), dtype=np.float32)
    for index, image in enumerate(images):
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if metadata.get("resize_mode") == "letterbox":
            h, w = rgb.shape[:2]
            scale = min(size / w, size / h)
            nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
            resized = cv2.resize(
                rgb,
                (nw, nh),
                interpolation=cv2.INTER_AREA if scale <= 1 else cv2.INTER_LINEAR,
            )
            canvas = np.zeros((size, size, 3), dtype=np.uint8)
            x, y = (size - nw) // 2, (size - nh) // 2
            canvas[y : y + nh, x : x + nw] = resized
            rgb = canvas
        else:
            rgb = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_AREA)
        batch[index] = (rgb.astype(np.float32).transpose(2, 0, 1) / 255 - mean) / std
    return batch


@dataclass
class UnitDetailRegions:
    health_bar: tuple
    star_badge: np.ndarray
    item_strip: np.ndarray
    item_icons: list


def _health_bar_candidates(crop: np.ndarray) -> list[tuple[int, int, int, int]]:
    if crop is None or crop.size == 0:
        return []
    height, width = crop.shape[:2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(
        hsv,
        np.array([45, 160, 45], dtype=np.uint8),
        np.array([78, 255, 255], dtype=np.uint8),
    )
    kernel_width = max(3, width // 18)
    if kernel_width % 2 == 0:
        kernel_width += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_width, 1))
    green = cv2.morphologyEx(green, cv2.MORPH_CLOSE, kernel)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(green)
    candidates: list[tuple[int, int, int, int]] = []
    for x, y, bar_width, bar_height, area in stats[1:count]:
        if not (
            bar_width >= width * 0.22
            and 2 <= bar_height <= max(3, height * 0.14)
            and y < height * 0.65
            and bar_width / max(1, bar_height) >= 4.0
            and area >= bar_width * bar_height * 0.30
        ):
            continue
        candidates.append((int(x), int(y), int(bar_width), int(bar_height)))
    return candidates


def extract_unit_detail_regions(crop: np.ndarray | None) -> UnitDetailRegions | None:
    """Extract health-bar-relative regions without assuming screen resolution.

    The star marker is immediately left of the player health bar. Equipped item
    icons occupy the wider status area around and above that bar. The crops are
    deliberately generous until reviewed positive examples establish tighter
    Set 18 geometry.
    """
    if crop is None or crop.size == 0:
        return None
    candidates = _health_bar_candidates(crop)
    if not candidates:
        return None
    x, y, bar_width, bar_height = max(candidates, key=lambda box: box[2] * box[3])
    height, width = crop.shape[:2]

    star_x1 = max(0, int(round(x - bar_width * 0.35)))
    star_x2 = min(width, int(round(x + bar_width * 0.08)))
    star_y1 = max(0, int(round(y - bar_width * 0.08)))
    star_y2 = min(height, int(round(y + bar_height + bar_width * 0.16)))

    # Equipped icons sit below the health bar and may begin left of its green
    # fill. The earlier region spent most of its height above the bar and cut
    # the icons off after their first few pixels. Retain the rank frame at the
    # left plus a full icon-height below the bar.
    item_x1 = max(0, int(round(x - bar_width * 0.35)))
    item_x2 = min(width, int(round(x + bar_width * 1.08)))
    item_y1 = max(0, int(round(y - bar_width * 0.10)))
    item_y2 = min(height, int(round(y + bar_height + bar_width * 0.60)))
    if star_x2 <= star_x1 or star_y2 <= star_y1 or item_y2 <= item_y1:
        return None
    icon_size = max(1, int(round(bar_width * 0.36)))
    # Anchor below the detected green fill's bottom. Its top/height can vary
    # by a couple of pixels with compression and animation, while the lower
    # edge stays aligned with the status frame.
    icon_y = y + bar_height + int(round(bar_width * 0.095))
    icon_x_offsets = (-0.08, 0.32, 0.706)
    item_icons = [
        crop[icon_y : icon_y + icon_size, icon_x : icon_x + icon_size].copy()
        for offset in icon_x_offsets
        for icon_x in (int(round(x + bar_width * offset)),)
        if (
            icon_x >= 0
            and icon_y >= 0
            and icon_x + icon_size <= width
            and icon_y + icon_size <= height
        )
    ]
    return UnitDetailRegions(
        health_bar=(x, y, bar_width, bar_height),
        star_badge=crop[star_y1:star_y2, star_x1:star_x2].copy(),
        item_strip=crop[item_y1:item_y2, item_x1:item_x2].copy(),
        item_icons=item_icons,
    )


def extract_item_icon_slots(item_strip: np.ndarray | None) -> list[np.ndarray]:
    """Split a health-bar-relative strip into its three equipped-icon slots.

    The ratios come from the 1440p Set 18 review set and scale with the strip
    height, which itself scales from the detected health-bar width. A clipped
    right edge simply omits the unavailable slot instead of matching a partial
    icon.
    """
    if item_strip is None or item_strip.size == 0:
        return []
    height, width = item_strip.shape[:2]
    size = max(1, int(round(height * 0.47)))
    x0 = int(round(height * 0.35))
    y0 = int(round(height * 0.35))
    pitch = max(1, int(round(height * 0.51)))
    if y0 + size > height:
        return []
    return [
        item_strip[y0 : y0 + size, x : x + size].copy()
        for slot in range(3)
        for x in (x0 + slot * pitch,)
        if x + size <= width
    ]
