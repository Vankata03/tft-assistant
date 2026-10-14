"""Carry positive physical bounds and reviewed anchor calibration to the shell.

Electron performs native per-monitor DIP conversion. The core never supplies a
made-up desktop origin or treats a previous window's rectangle as current.
"""
from typing import Literal
from pydantic import AwareDatetime, Field, StrictInt
from tft_core.baseline.contracts import DisplayModel, SurfaceAnchor


class PhysicalClientBounds(DisplayModel):
    x: StrictInt
    y: StrictInt
    width: StrictInt = Field(gt=0, le=20000)
    height: StrictInt = Field(gt=0, le=20000)


class LiveSurfaceAnchor(SurfaceAnchor):
    kind: Literal['shop','level','par','augment','carousel','wisp','xp','player','hex','line','review']
    index: StrictInt = Field(ge=0, le=27)


class SurfaceCalibration(DisplayModel):
    client_size: tuple[StrictInt, StrictInt]
    ui_scale: float = Field(ge=.5, le=1.5, allow_inf_nan=False)


class SurfaceGeometry(DisplayModel):
    window_id: str
    coordinate_space: Literal['physical_pixels']
    client_bounds: PhysicalClientBounds
    read_at: AwareDatetime
    layout_read_at: AwareDatetime
    layout_source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    source: Literal['Win32-client-rectangle']
    window_mode: Literal['windowed','borderless','exclusive_fullscreen','unknown']
    ui_scale: float = Field(ge=.5, le=1.5, allow_inf_nan=False)
    profile_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    calibration: SurfaceCalibration


def captured_surface(snapshot):
    """Return checked wire geometry/anchors; unread metadata has no fallback."""
    if not snapshot:
        return None, ()
    geometry, profile, layout = (snapshot.get(name) for name in ('capture_geometry','surface_profile','capture_layout'))
    if not geometry or not profile or not layout or layout.get('scale_source') != 'game-config' or not layout.get('read_at') or not layout.get('config_sha256'):
        return None, ()
    view = SurfaceGeometry(**geometry, layout_read_at=layout['read_at'], layout_source_sha256=layout['config_sha256'], window_mode=layout['window_mode'], ui_scale=layout['ui_scale'],
                           profile_sha256=profile['profile_sha256'], calibration=profile['calibration'])
    anchors = tuple(LiveSurfaceAnchor(**row) for row in profile['anchors'])
    return view, anchors
