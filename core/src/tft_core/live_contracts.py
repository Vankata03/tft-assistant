"""Finite ranked display contracts; full distributions remain referenced evidence."""

from typing import Literal
from pydantic import AwareDatetime, Field, JsonValue, model_validator
from tft_core.baseline.contracts import DisplayModel


class LiveOptionDisplay(DisplayModel):
    option_id: str
    action: str
    expected_placement: float | None = Field(allow_inf_nan=False)
    standard_error: float | None = Field(allow_inf_nan=False)
    reason: str
    payload: dict[str, JsonValue]
    evidence_path: tuple[str | int, ...]


class LiveAdviceDisplay(DisplayModel):
    decision_id: str
    option_id: str
    domain: str
    action: str
    urgency: Literal['act_this_phase', 'soon', 'information']
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str
    numbers: dict[str, float | int | str]
    placement_impact: float = Field(allow_inf_nan=False)
    payload: dict[str, JsonValue]
    anchors: dict[str, JsonValue]
    validity: tuple[str, ...]
    valid_until: AwareDatetime | None
    evidence_path: tuple[str | int, ...]
    options: tuple[LiveOptionDisplay, ...]


class LiveLineDisplay(DisplayModel):
    comp_id: str
    line_id: str
    seed: str
    expected_placement: float = Field(allow_inf_nan=False)
    standard_error: float = Field(ge=0, allow_inf_nan=False)
    hit_probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    death_probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    schedule: dict[str, JsonValue]
    evidence_path: tuple[str | int, ...]


class LiveProjectionDisplay(DisplayModel):
    round_id: str
    gold: float = Field(allow_inf_nan=False)
    level: float = Field(allow_inf_nan=False)
    hit_probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    hp: float = Field(allow_inf_nan=False)
    expected_placement: float = Field(allow_inf_nan=False)
    planned_gold: float | None = Field(allow_inf_nan=False)


class LiveFitDisplay(DisplayModel):
    comp_id: str
    score: float = Field(allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    evidence_path: tuple[str | int, ...]


class LiveNextPlanningPreview(DisplayModel):
    """Combat's preview of the next planning call: a scheduled point, never projected state."""
    available: bool
    reason: str | None
    comp_id: str | None
    line_id: str | None
    pinned: bool
    planning_round: str | None
    planning_snapshot_id: str | None
    round_id: str | None
    level: int | None
    gold_floor: float | None = Field(allow_inf_nan=False)
    evidence_path: tuple[str | int, ...]

    @model_validator(mode="after")
    def qualified_point(self):
        provenance = (self.comp_id, self.line_id, self.planning_round, self.planning_snapshot_id, self.round_id)
        if self.available and (self.reason is not None or None in provenance
                               or (self.level is None and self.gold_floor is None)):
            raise ValueError("An available preview names its plan, provenance and scheduled point")
        if not self.available and (not self.reason or self.pinned or any(value is not None for value in provenance)
                                   or self.level is not None or self.gold_floor is not None):
            raise ValueError("An unavailable preview names only its reason")
        return self


class LiveContent(DisplayModel):
    game_id: str
    snapshot_id: str
    captured_at: AwareDatetime
    evaluated_at: AwareDatetime
    data_snapshot_id: str | None
    model_hash: str | None
    round_id: str
    phase: Literal['planning', 'roll_down', 'augment', 'carousel', 'combat', 'end', 'unknown']
    advice: tuple[LiveAdviceDisplay, ...]
    plan: dict[str, JsonValue]
    lines: tuple[LiveLineDisplay, ...]
    projection: tuple[LiveProjectionDisplay, ...]
    recommended_board: dict[str, JsonValue] | None
    fits: tuple[LiveFitDisplay, ...]
    roster_valid_until: AwareDatetime | None = None
    ownership_valid_until: AwareDatetime | None = None
    opponents: tuple[dict[str, JsonValue], ...] = ()
    roll_tracker: dict[str, JsonValue] | None = None
    next_planning: LiveNextPlanningPreview | None = None
    confidence_medium_min: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    entity_names: dict[str, str] = {}
    warnings: tuple[str, ...] = ()
    evidence_id: str
