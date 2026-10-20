"""HUD rectangles anchored to the game client area, never desktop coordinates.

The reference rectangles come from the committed 2560x1440 probe frames. Their
width and offsets scale with client height and the game's UI scale. A wider
client keeps the central HUD centered and side panels attached to their edges.
Geometry support is distinct from verified OCR accuracy at a new layout.
"""
import configparser
import math
import hashlib
import tomllib
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

MEASURED_HUD_FORMAT = "tft-assistant-measured-hud/1"
_STANDALONE_SECTION = "/Script/TFTSettings.TFTUserSettings"
# x0,y0,x1,y1 at the reference resolution; horizontal and vertical anchors.
_REGIONS = {
    # The top bar narrows in stage 1. Stage spans both bar widths; its parser
    # accepts one round match among icons. Timer fits the stage-2+ digits only.
    # Both keep vertical margin, which the OCR detector needs.
    "stage": ((.3969, 0, .4477, .0347), "center", "top"),
    "timer": ((.5883, 0, .6078, .0444), "center", "top"),
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
    read_at: str | None = None
    config_sha256: str | None = None

    def __post_init__(self):
        if not math.isfinite(self.ui_scale) or not .5 <= self.ui_scale <= 1.5:
            raise ValueError("Unsupported UI scale; calibration requires a finite scale from 0.5 to 1.5")

    @classmethod
    def from_config(cls, path: Path):
        path = Path(path)
        raw = path.read_bytes()
        if not raw:
            raise ValueError(f"Game UI configuration unavailable: {path}")
        try:
            record = tomllib.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, tomllib.TOMLDecodeError):
            record = {}
        if record.get("format") == MEASURED_HUD_FORMAT:
            return cls._from_measured(path, raw, record)
        config = configparser.ConfigParser(strict=False, interpolation=None)
        try:
            config.read_string(raw.decode('utf-8'))
            if config.has_section(_STANDALONE_SECTION):
                raise ValueError("The standalone TFT client settings carry no HUD scale; "
                                 "point game_config at a measured HUD record")
        except configparser.Error as error:
            raise ValueError('Game UI configuration is unreadable; revalidate its layout') from error
        config = configparser.ConfigParser()
        try:
            config.read_string(raw.decode('utf-8'))
        except configparser.Error as error:
            raise ValueError('Game UI configuration is unreadable; revalidate its layout') from error
        try:
            scale = config.getfloat("HUD", "GlobalScale")
        except (ValueError, configparser.Error) as error:
            raise ValueError("Game configuration has no readable HUD GlobalScale; verify the new-client layout") from error
        mode = config.getint("General", "WindowMode", fallback=-1)
        return cls(scale, {0: "exclusive_fullscreen", 1: "windowed", 2: "borderless"}.get(mode, "unknown"), "game-config", datetime.now(timezone.utc).isoformat(), hashlib.sha256(raw).hexdigest())

    @classmethod
    def _from_measured(cls, path: Path, raw: bytes, record: dict):
        # The standalone client stores window mode but no HUD scale, so the scale
        # comes from a reviewed measurement against the probe reference frames.
        scale = record.get("hud_scale")
        settings = record.get("client_settings")
        if (set(record) != {"format", "client_settings", "hud_scale"} or not isinstance(settings, str)
                or not isinstance(scale, dict) or set(scale) != {"value", "measured_at", "client_size", "method"}
                or type(scale["value"]) is not float or not isinstance(scale["method"], str) or not scale["method"].strip()
                or not isinstance(scale["measured_at"], str) or not scale["measured_at"].strip()
                or not isinstance(scale["client_size"], list) or len(scale["client_size"]) != 2
                or any(type(side) is not int or side <= 0 for side in scale["client_size"])):
            raise ValueError("Measured HUD record requires client_settings and hud_scale value, measured_at, client_size and method")
        settings_path = (path.parent / settings).resolve()
        client = settings_path.read_bytes()
        config = configparser.ConfigParser(strict=False, interpolation=None)
        try:
            config.read_string(client.decode('utf-8'))
            mode = config.getint(_STANDALONE_SECTION, "FullscreenMode")
        except (UnicodeDecodeError, ValueError, configparser.Error) as error:
            raise ValueError(f"Measured HUD record needs readable standalone client settings: {settings_path}") from error
        # Unreal EWindowMode: Fullscreen, WindowedFullscreen, Windowed.
        window_mode = {0: "exclusive_fullscreen", 1: "borderless", 2: "windowed"}.get(mode, "unknown")
        identity = hashlib.sha256(hashlib.sha256(raw).digest() + hashlib.sha256(client).digest()).hexdigest()
        return cls(scale["value"], window_mode, "measured", datetime.now(timezone.utc).isoformat(), identity)

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
                "window_mode": self.window_mode, "size": list(size),
                "read_at": self.read_at, "config_sha256": self.config_sha256}
