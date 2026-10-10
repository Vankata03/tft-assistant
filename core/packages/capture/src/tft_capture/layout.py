"""HUD rectangles anchored to the game client area, never desktop coordinates.

The reference rectangles come from the committed 2560x1440 probe frames. Their
width and offsets scale with client height and the game's UI scale. A wider
client keeps the central HUD centered and side panels attached to their edges.
Geometry support is distinct from verified OCR accuracy at a new layout.
"""
import configparser
import math
from dataclasses import dataclass
from pathlib import Path

# x0,y0,x1,y1 at the reference resolution; horizontal and vertical anchors.
_REGIONS = {
    "stage": ((.419, .002, .457, .036), "center", "top"),
    "timer": ((.557, .002, .585, .036), "center", "top"),
    "level": ((.181, .811, .232, .851), "center", "bottom"),
    "xp": ((.244, .811, .273, .851), "center", "bottom"),
    "odds": ((.288, .811, .443, .851), "center", "bottom"),
    "gold": ((.529, .811, .556, .851), "center", "bottom"),
    "streak": ((.595, .811, .611, .851), "center", "bottom"),
    "shop": ((.287, .854, .813, 1), "center", "bottom"),
    "traits": ((.03, .235, .137, .74), "left", "top"),
    "players": ((.868, .14, 1, .758), "right", "top"),
    "scouted": ((.25, .08, .80, .70), "center", "top"),
    "cards": ((.184, .225, .815, .83), "center", "center"),
    "board": ((.15, .09, .855, .797), "center", "center"),
}


@dataclass(frozen=True)
class HudLayout:
    ui_scale: float = 1.0
    window_mode: str = "unknown"
    scale_source: str = "probe-reference"

    def __post_init__(self):
        if not math.isfinite(self.ui_scale) or not .5 <= self.ui_scale <= 1.5:
            raise ValueError("Unsupported UI scale; calibration requires a finite scale from 0.5 to 1.5")

    @classmethod
    def from_config(cls, path: Path):
        config = configparser.ConfigParser()
        if not config.read(path, encoding="utf-8"):
            raise ValueError(f"Game UI configuration unavailable: {path}")
        try:
            scale = config.getfloat("HUD", "GlobalScale")
        except (ValueError, configparser.Error) as error:
            raise ValueError("Game configuration has no readable HUD GlobalScale; verify the new-client layout") from error
        mode = config.getint("General", "WindowMode", fallback=-1)
        return cls(scale, {0: "exclusive_fullscreen", 1: "windowed", 2: "borderless"}.get(mode, "unknown"), "game-config")

    def regions(self, size: tuple[int, int]) -> dict[str, tuple[float, float, float, float]]:
        width, height = size
        if width <= 0 or height <= 0:
            raise ValueError("Game client has no drawable area")
        scale = height / 1440 * self.ui_scale
        result = {}
        for name, (rectangle, horizontal, vertical) in _REGIONS.items():
            x0, y0, x1, y1 = rectangle
            horizontal_origin = {"left": 0, "center": width/2, "right": width}[horizontal]
            reference_x = {"left": 0, "center": 1280, "right": 2560}[horizontal]
            vertical_origin = {"top": 0, "center": height/2, "bottom": height}[vertical]
            reference_y = {"top": 0, "center": 720, "bottom": 1440}[vertical]
            result[name] = (max(0, (horizontal_origin + (x0*2560-reference_x)*scale)/width),
                            max(0, (vertical_origin + (y0*1440-reference_y)*scale)/height),
                            min(1, (horizontal_origin + (x1*2560-reference_x)*scale)/width),
                            min(1, (vertical_origin + (y1*1440-reference_y)*scale)/height))
        return result

    def describe(self, size: tuple[int, int]) -> dict:
        return {"ui_scale": self.ui_scale, "scale_source": self.scale_source,
                "window_mode": self.window_mode, "size": list(size)}
