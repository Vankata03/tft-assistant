"""Display-only Baseline wire contracts. Opponent boards have no representation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DisplayModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, json_schema_serialization_defaults_required=True
    )


class EntityDisplay(DisplayModel):
    id: str
    name: str
    icon: str = ""
    cost: int = 0


class LayoutUnit(DisplayModel):
    entity: EntityDisplay
    position: int | None = Field(default=None, ge=0, le=27)


class GuideSummary(DisplayModel):
    id: str
    name: str
    tier: str
    units: tuple[EntityDisplay, ...]


class GuideDisplay(GuideSummary):
    early_layout: tuple[LayoutUnit, ...]
    final_layout: tuple[LayoutUnit, ...]
    stage_tips: dict[str, str]
    stage_plan: tuple[dict[str, str | int | float], ...]
    carousel: tuple[EntityDisplay, ...]
    alternatives: tuple[str, ...]


class RecipeComponent(DisplayModel):
    entity: EntityDisplay
    held: bool


class ItemRecipe(DisplayModel):
    unit: EntityDisplay
    item: EntityDisplay
    components: tuple[RecipeComponent, ...]


class ShopHighlight(DisplayModel):
    slot: int = Field(ge=0, le=4)
    entity: EntityDisplay
    in_guide: bool


class AugmentTier(DisplayModel):
    entity: EntityDisplay
    tier: str | None
    global_tier: str | None
    in_guide: bool
    offered: bool = False
    offer_index: int | None = Field(default=None, ge=0, le=20)


class WispWorth(DisplayModel):
    entity: EntityDisplay
    worth: float | None
    source: str
    offered_slot: int | None = Field(default=None, ge=0, le=4)


class XpHint(DisplayModel):
    target_level: int
    target_round: str
    buys: int
    gold: int
    passive_xp: int
    text: str


class ParChance(DisplayModel):
    probability: float | None = Field(default=None, ge=0, le=1)
    paused: str | None = None
    uncertain: bool = False


class FacedResult(DisplayModel):
    name: str
    result: Literal["win", "loss", "draw"]


class PausedField(DisplayModel):
    field: str
    age_seconds: float | None = None
    reason: str


class StageVoice(DisplayModel):
    id: str
    text: str


class SurfaceAnchor(DisplayModel):
    kind: Literal["shop", "level", "par", "augment", "carousel", "wisp"]
    index: int = Field(default=0, ge=0, le=20)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside_frame(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Surface anchor extends beyond the captured frame")
        return self


class OverlayBounds(DisplayModel):
    x: int
    y: int
    width: int = Field(gt=0, le=20000)
    height: int = Field(gt=0, le=20000)


class BaselineContent(DisplayModel):
    patch: str
    snapshot_id: str
    round_id: str | None
    guides: tuple[GuideSummary, ...]
    selected: GuideDisplay | None
    xp_hint: XpHint | None
    par: ParChance
    shop: tuple[ShopHighlight, ...]
    recipes: tuple[ItemRecipe, ...]
    augments: tuple[AugmentTier, ...]
    wisps: tuple[WispWorth, ...]
    faced: tuple[FacedResult, ...]
    warnings: tuple[str, ...]
    phase: Literal[
        "planning", "roll_down", "augment", "carousel", "combat", "end", "unknown"
    ] = "unknown"
    anchors: tuple[SurfaceAnchor, ...] = ()
    overlay_bounds: OverlayBounds | None = None
    overlay_allowed: bool = False


class BaselineState(DisplayModel):
    v: Literal[1] = 1
    type: Literal["baseline_state"] = "baseline_state"
    mode: Literal["silent", "baseline", "live"]
    status: str
    stale: tuple[PausedField, ...] = ()
    content: BaselineContent | None = None
    voice: StageVoice | None = None

    @model_validator(mode="after")
    def enforce_mode(self):
        if self.mode != "baseline" and (
            self.content is not None or self.voice is not None
        ):
            raise ValueError("Baseline content and voice require Baseline mode")
        return self
