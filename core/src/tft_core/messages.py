"""Messages between the core and the shell, defined once.

Every message is a JSON object with a schema version `v` and a `type`. JSON
Schema generated from these models (`uv run tft-schemas`) lives in
`schemas/messages.schema.json`, and the shell's TypeScript types are generated
from that file, so the two sides cannot drift.
"""

import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, RootModel, TypeAdapter, JsonValue, StrictInt, model_validator

from tft_core.baseline.contracts import BaselineState
from tft_core.live_contracts import LiveContent
from tft_core.surface_geometry import SurfaceGeometry, LiveSurfaceAnchor

SCHEMA_VERSION = 1


class SessionMode(StrEnum):
    """The mode the coach runs a game in. Stage 1 wires the selector only."""

    SILENT = "silent"
    BASELINE = "baseline"
    LIVE = "live"


class _Message(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_serialization_defaults_required=True,
    )

    v: Literal[1] = SCHEMA_VERSION


# Shell to core.


class Hello(_Message):
    """First message on every connection; the core closes it on a wrong token."""

    type: Literal["hello"] = "hello"
    token: str


class SetSessionMode(_Message):
    """The owner picked a session mode in the tray menu."""

    type: Literal["set_session_mode"] = "set_session_mode"
    mode: SessionMode


class RequestBaselineState(_Message):
    type: Literal["request_baseline_state"] = "request_baseline_state"


class SelectGuide(_Message):
    type: Literal["select_guide"] = "select_guide"
    guide_id: str = Field(min_length=1, max_length=200)


class SurfaceShown(_Message):
    type: Literal["surface_shown"] = "surface_shown"
    surface: Literal["cockpit", "overlay", "voice"]
    content_id: str = Field(min_length=1, max_length=500)
    timestamp: AwareDatetime


class RequestLiveState(_Message):
    type: Literal["request_live_state"] = "request_live_state"


class RequestSurfaceGeometry(_Message):
    type: Literal["request_surface_geometry"] = "request_surface_geometry"


class RequestEvidencePage(_Message):
    type: Literal["request_evidence_page"] = "request_evidence_page"
    request_id: str = Field(min_length=1, max_length=100)
    game_id: str = Field(pattern=r"^[1-9][0-9]*$")
    revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    path: tuple[str | StrictInt, ...] = Field(max_length=64)
    cursor: StrictInt = Field(default=0, ge=0)
    limit: StrictInt = Field(default=32, ge=1, le=128)


class LiveSurfaceShown(_Message):
    type: Literal["live_surface_shown"] = "live_surface_shown"
    game_id: str = Field(pattern=r"^[1-9][0-9]*$")
    revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    decision_id: str = Field(min_length=1, max_length=500)
    option_id: str = Field(max_length=500)
    surface: Literal["cockpit", "overlay", "voice"]
    timestamp: AwareDatetime


class PinLine(_Message):
    type: Literal["pin_line"] = "pin_line"
    game_id: str = Field(pattern=r"^[1-9][0-9]*$")
    revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    comp_id: str | None = Field(default=None, min_length=1, max_length=200)
    line_id: str | None = Field(default=None, min_length=1, max_length=200)
    seed: str | None = Field(default=None, pattern=r"^[0-9]{1,20}$")

    @model_validator(mode="after")
    def complete_reference(self):
        if len({self.comp_id is None, self.line_id is None, self.seed is None}) != 1:
            raise ValueError("Line pin requires all reference fields or none to unpin")
        return self


# Core to shell.


class Gameflow(_Message):
    """The League client's state and gameflow phase.

    `phase` is the client's phase string as reported (`Lobby`, `ChampSelect`,
    `InProgress`, `Reconnect`, `PreEndOfGame` and so on); null when the client
    is not running or reports no phase.
    """

    type: Literal["gameflow"] = "gameflow"
    client_running: bool
    phase: str | None


class SessionModeState(_Message):
    """The session mode the core holds; sent on connect and on every change."""

    type: Literal["session_mode"] = "session_mode"
    mode: SessionMode
    available_modes: tuple[SessionMode, ...] = tuple(SessionMode)


class ErrorMessage(_Message):
    request_id: str | None = None
    """The core rejected a message from the shell."""

    type: Literal["error"] = "error"
    code: str
    message: str


class LiveState(_Message):
    type: Literal["live_state"] = "live_state"
    mode: SessionMode
    status: str
    revision: str | None = None
    content: LiveContent | None = None
    pin: dict[str, str] | None = None
    invalidated: dict[str, str] = {}
    next_planning_invalidated: str | None = None
    roster_qualified: bool | None = None
    ownership_qualified: bool | None = None
    observed_phase: Literal['planning','roll_down','augment','carousel','combat','end','unknown'] | None = None

    @model_validator(mode="after")
    def permitted_content(self):
        if self.mode != SessionMode.LIVE and self.content is not None:
            raise ValueError("Live content requires Live mode")
        json.dumps(self.model_dump(mode="json"), allow_nan=False)
        return self


class ReviewReady(_Message):
    type: Literal['review_ready'] = 'review_ready'
    game_id: str = Field(pattern=r'^[1-9][0-9]*$')
    mode: Literal['baseline','live']
    report_id: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    evidence_id: str = Field(pattern=r'^sha256:[0-9a-f]{64}$')
    ended_at: AwareDatetime
    ready_at: AwareDatetime
    latency_seconds: float = Field(ge=0, allow_inf_nan=False)
    late: bool


class EvidencePage(_Message):
    type: Literal["evidence_page"] = "evidence_page"
    request_id: str
    game_id: str
    revision: str
    page: dict[str, JsonValue]


class SurfaceGeometryState(_Message):
    type: Literal["surface_geometry"] = "surface_geometry"
    mode: SessionMode
    geometry: SurfaceGeometry | None = None
    anchors: tuple[LiveSurfaceAnchor, ...] = ()
    status: str = "Desktop geometry unavailable"

    @model_validator(mode="after")
    def permitted_geometry(self):
        if self.mode is SessionMode.SILENT and (self.geometry is not None or self.anchors):
            raise ValueError("Silent mode suppresses surface geometry")
        if self.mode is SessionMode.BASELINE and any(row.kind in ('player', 'hex', 'line', 'xp') for row in self.anchors):
            raise ValueError("Baseline geometry cannot include ranked or player-row anchors")
        return self


class RequestReviewGames(_Message):
    type: Literal['request_review_games'] = 'request_review_games'
    request_id: str = Field(min_length=1,max_length=100)


class ReviewGames(_Message):
    type: Literal['review_games'] = 'review_games'
    request_id: str
    games: tuple[dict[str,JsonValue],...]
    aggregates: dict[str,JsonValue] = Field(default_factory=dict)


class RequestReview(_Message):
    type: Literal['request_review'] = 'request_review'
    request_id: str = Field(min_length=1,max_length=100)
    game_id: str = Field(pattern=r'^[1-9][0-9]*$')
    operation: Literal['summary','page','what_if','tag','media','regenerate']
    report_id: str | None = None
    evidence_id: str | None = None
    path: tuple[str | StrictInt,...] = Field(default=(),max_length=64)
    cursor: StrictInt = Field(default=0,ge=0)
    limit: StrictInt = Field(default=32,ge=1,le=49152)
    moment_id: str | None = Field(default=None,max_length=500)
    option_id: str | None = Field(default=None,max_length=500)
    tag: Literal['agree','disagree','unsure'] | None = None
    name: str | None = Field(default=None,pattern=r'^media/[0-9a-f]{32}\.(webp|mp4)$')

    @model_validator(mode='after')
    def required_arguments(self):
        if any(isinstance(part,str) and len(part)>500 or type(part) is int and part<0 for part in self.path):
            raise ValueError('Invalid review evidence path')
        if self.operation not in ('summary','media','regenerate') and (not self.report_id or not self.evidence_id):
            raise ValueError('Review details require the current report and evidence identities')
        if self.operation in ('tag','what_if') and not self.moment_id:
            raise ValueError('Known review moment required')
        if self.operation=='tag' and not self.tag:raise ValueError('Review tag required')
        if self.operation=='what_if' and not self.option_id:raise ValueError('Known scored option required')
        if self.operation=='media' and not self.name:raise ValueError('Logged media name required')
        if self.operation=='page' and self.limit>128:raise ValueError('Review page limit exceeds 128')
        return self


class ReviewResponse(_Message):
    type: Literal['review_response'] = 'review_response'
    request_id: str
    game_id: str
    operation: Literal['summary','page','what_if','tag','media','regenerate']
    value: dict[str,JsonValue]


class UiMessage(
    RootModel[
        Annotated[
            Hello | SetSessionMode | RequestBaselineState | SelectGuide | SurfaceShown | RequestLiveState | RequestEvidencePage | LiveSurfaceShown | PinLine | RequestSurfaceGeometry | RequestReview | RequestReviewGames,
            Field(discriminator="type"),
        ]
    ]
):
    """Any message the shell sends to the core."""


class CoreMessage(
    RootModel[
        Annotated[
            Gameflow | SessionModeState | ErrorMessage | BaselineState | LiveState | EvidencePage | SurfaceGeometryState | ReviewResponse | ReviewGames | ReviewReady,
            Field(discriminator="type"),
        ]
    ]
):
    """Any message the core sends to the shell."""


class UnsupportedVersion(ValueError):
    pass


_ui_adapter = TypeAdapter(UiMessage)
_core_adapter = TypeAdapter(CoreMessage)


def _check_version(raw: str | bytes) -> object:
    data = json.loads(raw)
    if not isinstance(data, dict) or (type(data.get("v")) is not int or data.get("v") != SCHEMA_VERSION):
        version = data.get("v") if isinstance(data, dict) else None
        raise UnsupportedVersion(
            f"expected schema version {SCHEMA_VERSION}, got {version!r}"
        )
    return data


def parse_ui_message(
    raw: str | bytes,
) -> Hello | SetSessionMode | RequestBaselineState | SelectGuide | SurfaceShown:
    """Parse a message from the shell; raises UnsupportedVersion or pydantic.ValidationError."""
    return _ui_adapter.validate_python(_check_version(raw)).root


def parse_core_message(
    raw: str | bytes,
) -> Gameflow | SessionModeState | ErrorMessage | BaselineState:
    """Parse a message from the core; raises UnsupportedVersion or pydantic.ValidationError."""
    return _core_adapter.validate_python(_check_version(raw)).root


def dump(message: BaseModel) -> str:
    return message.model_dump_json()
