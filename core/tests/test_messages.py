import json

import jsonschema
import pytest
from pydantic import ValidationError

from tft_core.messages import (
    ErrorMessage,
    Gameflow,
    Hello,
    SessionMode,
    SessionModeState,
    SetSessionMode,
    UnsupportedVersion,
    dump,
    parse_core_message,
    parse_ui_message,
)
from tft_core.schemas import SCHEMA_PATH, build_schema, render_schema

CORE_MESSAGES = [
    Gameflow(client_running=True, phase="InProgress"),
    Gameflow(client_running=False, phase=None),
    SessionModeState(mode=SessionMode.LIVE),
    ErrorMessage(code="invalid_message", message="bad"),
]
UI_MESSAGES = [
    Hello(token="abc"),
    SetSessionMode(mode=SessionMode.BASELINE),
]


def _validator(definition: str) -> jsonschema.Validator:
    schema = build_schema()
    return jsonschema.Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]})


@pytest.mark.parametrize("message", CORE_MESSAGES, ids=repr)
def test_core_message_round_trip(message):
    raw = dump(message)
    assert parse_core_message(raw) == message
    _validator("CoreMessage").validate(json.loads(raw))


@pytest.mark.parametrize("message", UI_MESSAGES, ids=repr)
def test_ui_message_round_trip(message):
    raw = dump(message)
    assert parse_ui_message(raw) == message
    _validator("UiMessage").validate(json.loads(raw))


def test_every_message_carries_version_and_type():
    for message in CORE_MESSAGES + UI_MESSAGES:
        data = json.loads(dump(message))
        assert data["v"] == 1
        assert isinstance(data["type"], str)


@pytest.mark.parametrize("raw", ['{"type": "hello", "token": "a"}', '{"v": 2, "type": "hello", "token": "a"}', "[]"])
def test_rejects_other_versions(raw):
    with pytest.raises(UnsupportedVersion):
        parse_ui_message(raw)


@pytest.mark.parametrize(
    "raw",
    [
        '{"v": 1, "type": "set_session_mode", "mode": "turbo"}',
        '{"v": 1, "type": "gameflow", "client_running": true, "phase": "Lobby"}',
        '{"v": 1, "type": "hello", "token": "a", "extra": 1}',
    ],
)
def test_rejects_invalid_ui_messages(raw):
    with pytest.raises(ValidationError):
        parse_ui_message(raw)


def test_schema_requires_version_and_type():
    defs = build_schema()["$defs"]
    for name in ("Gameflow", "SessionModeState", "ErrorMessage", "Hello", "SetSessionMode"):
        assert {"v", "type"} <= set(defs[name]["required"]), name


def test_committed_schema_is_current():
    assert SCHEMA_PATH.read_text(encoding="utf-8") == render_schema(), "run `uv run tft-schemas`"
