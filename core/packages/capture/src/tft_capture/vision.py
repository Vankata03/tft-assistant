"""The visual-recognition boundary implemented by the reader ticket.

`fields` contains only positively observed values. Missing keys are unavailable,
not empty. Own board/bench identities must only be supplied for `own_view=True`.
Carousel and choice icons can be supplied independently of the viewed board.
"""
from dataclasses import dataclass
from typing import Protocol

from PIL import Image


@dataclass(frozen=True)
class VisionRead:
    fields: dict
    source: str
    confidence: float
    inventory_complete: bool = False

    def __post_init__(self):
        if not 0 <= self.confidence <= 1:
            raise ValueError("Vision confidence must be between zero and one")


class VisualReader(Protocol):
    source: str
    def read(self, image: Image.Image, *, regions: dict[str, tuple[int, int, int, int]],
             own_view: bool | None) -> VisionRead: ...
