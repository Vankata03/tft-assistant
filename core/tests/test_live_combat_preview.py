"""Combat's Live overlay previews the next planning call from a qualified plan."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import runpy

import pytest

FIXTURES = runpy.run_path(str(Path(__file__).parents[1] / "packages/engine/tests/test_planning.py"))
SCHEDULE = {"id": "fixed", "levels": {"4-1": 6}, "rolls": {"4-2": 10}}


def frame(round_id="3-2", *, seconds=0, game_id="g", **changes):
    source = FIXTURES["snapshot"](round_id, **changes)
    moment = source.captured_at + timedelta(seconds=seconds)
    return replace(source, game_id=game_id, snapshot_id=f"{game_id}:{round_id}:{seconds}", captured_at=moment,
                   fields={name: replace(field, read_at=moment) for name, field in source.fields.items()})


def combat(round_id="3-2", *, seconds=1, **changes):
    changes.setdefault("pinned_line", SCHEDULE)
    current = frame(round_id, seconds=seconds, phase="combat", planning_phase=False, **changes)
    if changes["pinned_line"] is None:
        current = replace(current, fields={k: v for k, v in current.fields.items() if k != "pinned_line"})
    return current


def preview(current, *planning):
    from tft_engine import GameHistory
    from tft_live.advisor import LiveAdvisor

    delivery = LiveAdvisor().evaluate(current, GameHistory(tuple(planning)), FIXTURES["patch"](), mode="live")
    return delivery.content["next_planning"]


def test_combat_previews_the_next_scheduled_point_of_this_rounds_qualified_plan():
    planning = frame(pinned_line=SCHEDULE)
    shown = preview(combat(), planning)
    assert shown == {
        "available": True, "reason": None, "comp_id": "A", "line_id": "fixed", "pinned": True,
        "planning_round": "3-2", "planning_snapshot_id": "g:3-2:0", "round_id": "4-1", "level": 6, "gold_floor": None,
        "evidence_path": ["plan", "line"],
    }


def test_unpinned_preview_uses_the_engine_selected_guide_line():
    # Guide A schedules level 5 and a 10-gold roll-down at 3-1.
    shown = preview(combat("2-5", pinned_line=None), frame("2-5"))
    assert (shown["available"], shown["pinned"], shown["line_id"]) == (True, False, "guide:A")
    assert (shown["round_id"], shown["level"], shown["gold_floor"]) == ("3-1", 5, 10)


def test_combat_preview_names_a_scheduled_roll_point_without_projected_state():
    rolling = {"id": "roll-next", "levels": {}, "rolls": {"3-3": 10}}
    shown = preview(combat(pinned_line=rolling), frame(pinned_line=rolling))
    assert shown["available"] is True
    assert (shown["round_id"], shown["level"], shown["gold_floor"]) == ("3-3", None, 10)
    assert not {"gold", "hp", "expected_placement", "action"} & set(shown)


@pytest.mark.parametrize("case", ("no_planning", "earlier_round", "pin_differs", "pin_released", "schedule_ended"))
def test_combat_without_a_qualified_plan_for_this_round_is_explicitly_unavailable(case):
    planning = frame(pinned_line=SCHEDULE)
    if case == "no_planning":
        shown = preview(combat())
    elif case == "earlier_round":
        shown = preview(combat(), frame("3-1", pinned_line=SCHEDULE))
    elif case == "pin_differs":
        other = {"id": "other", "levels": {"4-1": 7}, "rolls": {}}
        shown = preview(combat(pinned_line=other), planning)
    elif case == "pin_released":
        shown = preview(combat(pinned_line=None), planning)
    else:
        ended = {"id": "ended", "levels": {"3-2": 5}, "rolls": {"3-2": 10}}
        shown = preview(combat(pinned_line=ended), frame(pinned_line=ended))
    assert shown["available"] is False
    assert shown["reason"]
    assert shown["round_id"] is None and shown["level"] is None and shown["gold_floor"] is None


def test_planning_and_non_combat_phases_carry_no_preview():
    assert preview(frame(pinned_line=SCHEDULE)) is None
    augment = frame(seconds=1, phase="augment", planning_phase=False, pinned_line=SCHEDULE)
    assert preview(augment, frame(pinned_line=SCHEDULE)) is None


def test_delivery_publishes_the_preview_and_expires_it_with_phase_round_plan_and_mode(tmp_path):
    from tft_core.messages import PinLine, SessionMode
    from tft_core.server import CoreServer
    from tft_core.storage import SessionStore
    from tft_engine import GameHistory
    from tft_live.advisor import LiveAdvisor

    data = FIXTURES["patch"]()
    sessions = SessionStore(tmp_path / "app", tmp_path / "config", live_installed=True)
    sessions.set_mode("live")
    sessions.start_game("123", data_snapshot_id=data.snapshot_id)
    server = CoreServer("token", sessions=sessions)
    planning, fight = frame(game_id="123", pinned_line=SCHEDULE), combat(game_id="123")

    def published():
        server.observe_live_capture(fight, data)
        server.publish_live(LiveAdvisor().evaluate(fight, GameHistory((planning,)), data, mode="live"))
        return server.live.state(sessions.mode)

    state = published()
    assert state.content.next_planning.available is True
    assert (state.content.next_planning.line_id, state.content.next_planning.round_id) == ("fixed", "4-1")
    assert state.next_planning_invalidated is None
    assert not any(row.domain == "next_planning" for row in state.content.advice)

    server.observe_live_capture(frame(seconds=2, game_id="123", pinned_line=SCHEDULE), data)
    assert server.live.state(sessions.mode).next_planning_invalidated == "new planning evidence"
    server.observe_live_capture(combat("3-3", seconds=3, game_id="123"), data)
    assert server.live.state(sessions.mode).next_planning_invalidated == "round or game changed"
    server.observe_live_capture(fight, data)
    assert server.live.state(sessions.mode).next_planning_invalidated is None

    server.live.pin_line(PinLine(game_id="123", revision=state.revision), sessions.mode)
    assert server.live.state(sessions.mode).next_planning_invalidated == "plan changed"
    assert published().next_planning_invalidated is None

    assert server.live.state(SessionMode.BASELINE).content is None
    assert server.live.state(SessionMode.SILENT).content is None


def test_preview_contract_rejects_unqualified_or_state_bearing_previews():
    from pydantic import ValidationError
    from tft_core.live_contracts import LiveNextPlanningPreview

    point = {"available": True, "reason": None, "comp_id": "A", "line_id": "fixed", "pinned": True,
             "planning_round": "3-2", "planning_snapshot_id": "g:3-2:0", "round_id": "4-1", "level": 6,
             "gold_floor": None, "evidence_path": ["plan", "line"]}
    LiveNextPlanningPreview(**point)
    for invalid in ({"planning_snapshot_id": None}, {"level": None}, {"reason": "late"},
                    {"available": False}, {"gold": 30}):
        with pytest.raises(ValidationError):
            LiveNextPlanningPreview(**point | invalid)
