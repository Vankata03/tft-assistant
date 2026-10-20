"""Planning or combat from the owner's board, without a phase label on screen.

The standalone client shows the same top bar in planning and combat. In PvP
rounds the enemy half of the owner's board is empty while planning and holds
the opponent's units, with red health bars, in combat. Planning is claimed only
in the round's first countdown, observed from the round's start; anything else
leaves the phase unavailable.
"""
import numpy as np

# 200 red pixels over the enemy half of a 2560x1440 board separated the 2026-10-20
# probe's PvP planning and combat frames; expressed as a fraction of that area.
RED_FRACTION = 2e-4


def enemy_side_bars(frame, board) -> bool:
    """Whether red health bars appear on the upper (enemy) half of the board."""
    left, top, right, bottom = board
    pixels = np.asarray(frame.crop((left, top, right, top + (bottom - top) // 2)).convert("RGB")).astype(int)
    if not pixels.size:
        return False
    red = (pixels[..., 0] > 170) & (pixels[..., 1] < 60) & (pixels[..., 2] < 60)
    return red.sum() >= RED_FRACTION * red.size


class CountdownTracker:
    """Index of the timer countdown within a round whose start was observed."""

    def __init__(self):
        self.round_id, self.index, self._last = None, None, None

    def observe(self, round_id, timer):
        if round_id is None:
            return
        if round_id != self.round_id:
            # Only a round change seen by this capture establishes the first countdown.
            self.index = 0 if self.round_id is not None else None
            self.round_id, self._last = round_id, None
        if timer is None:
            return
        # Any increase is a reset; an OCR slip then costs availability, not correctness.
        if self._last is not None and timer > self._last and self.index is not None:
            self.index += 1
        self._last = timer

    def reset(self):
        self.round_id, self.index, self._last = None, None, None

    def first(self, round_id) -> bool:
        return round_id == self.round_id and self.index == 0
