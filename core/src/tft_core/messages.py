"""Messages between the core and the shell, defined once.

Every message is a JSON object with a schema version `v` and a `type`. JSON
Schema generated from these models (`uv run tft-schemas`) lives in
`schemas/messages.schema.json`, and the shell's TypeScript types are generated
from that file, so the two sides cannot drift.
"""

import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, RootModel, TypeAdapter

from tft_core.baseline.contracts import BaselineState

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
    """The core rejected a message from the shell."""

    type: Literal["error"] = "error"
    code: str
    message: str


class UiMessage(
    RootModel[
        Annotated[
            Hello | SetSessionMode | RequestBaselineState | SelectGuide | SurfaceShown,
            Field(discriminator="type"),
        ]
    ]
):
    """Any message the shell sends to the core."""


class CoreMessage(
    RootModel[
        Annotated[
            Gameflow | SessionModeState | ErrorMessage | BaselineState,
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
    if not isinstance(data, dict) or data.get("v") != SCHEMA_VERSION:
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
