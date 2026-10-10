"""Static Guide surfaces and the two permitted own-state hints."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil, isfinite
from typing import Any

from tft_data import DataError, DataSnapshot
from tft_data.models import Guide, freeze
from tft_engine.allowlist import growth_curve_lookup, strength, win_probability

from .contracts import (
    AugmentTier,
    BaselineContent,
    BaselineState,
    EntityDisplay,
    FacedResult,
    GuideDisplay,
    GuideSummary,
    ItemRecipe,
    LayoutUnit,
    OverlayBounds,
    ParChance,
    PausedField,
    RecipeComponent,
    ShopHighlight,
    StageVoice,
    SurfaceAnchor,
    WispWorth,
    XpHint,
)

TIER_ORDER = {"S+": 0, "S": 1, "A": 2, "B": 3, "C": 4, "D": 5}


@dataclass(frozen=True)
class OwnUnit:
    unit_id: str
    stars: int
    items: tuple[str, ...]


@dataclass(frozen=True)
class OwnBoard:
    units: tuple[OwnUnit, ...]
    trait_counts: Mapping[str, int] | None


class BaselineController:
    def __init__(self) -> None:
        self.data: DataSnapshot | None = None
        self.snapshot: Mapping | None = None
        self.selected_id: str | None = None
        self.faced: tuple[FacedResult, ...] = ()
        self.status = "Data unavailable; waiting for validated patch data"
        self._round_start = False
        self.anchors = ()
        self.overlay_bounds = None
        self.overlay_allowed = False
        self._spoken: set[tuple[str, str]] = set()

    def update(
        self,
        *,
        data: DataSnapshot | None = None,
        snapshot: Mapping[str, Any] | None = None,
        faced: tuple[Mapping[str, str], ...] = (),
        status: str = "Capture OK",
        now: datetime | None = None,
        round_start: bool = False,
        anchors: tuple[Mapping[str, Any], ...] = (),
        overlay_bounds: Mapping[str, int] | None = None,
        overlay_allowed: bool = False,
    ) -> None:
        self.anchors = tuple(SurfaceAnchor.model_validate(row) for row in anchors)
        self.overlay_bounds = (
            OverlayBounds.model_validate(overlay_bounds) if overlay_bounds else None
        )
        self.overlay_allowed = (
            overlay_allowed is True and self.overlay_bounds is not None
        )
        self._round_start = round_start
        self.data = data
        self.snapshot = freeze(snapshot)
        # Validate precisely the only permitted opponent output: names and results.
        self.faced = tuple(FacedResult.model_validate(row) for row in faced)
        self.status = (
            status
            if data is not None or status != "Capture OK"
            else "Data unavailable; waiting for validated patch data"
        )
        if data is not None and self.selected_id not in data.guides:
            self.selected_id = None

    def select(self, guide_id: str) -> None:
        if self.data is None or guide_id not in self.data.guides:
            raise DataError("Guide unavailable in the validated data snapshot")
        self.selected_id = guide_id

    def state(self, mode: str, *, now: datetime | None = None) -> BaselineState:
        mode = str(mode)
        now = now or datetime.now(UTC)
        stale = []
        if self.snapshot:
            for name in ("board", "level", "xp", "gold", "shop", "components"):
                item = self.snapshot.get("fields", {}).get(name)
                if not item:
                    continue
                try:
                    age = (
                        now - datetime.fromisoformat(item["read_at"])
                    ).total_seconds()
                    thresholds = (
                        self.data.tunables.get("field_max_age_seconds")
                        if self.data
                        else None
                    )
                    thresholds = thresholds.value if thresholds else {}
                    limit = (
                        thresholds.get(name, 2)
                        if isinstance(thresholds, Mapping)
                        else float(thresholds)
                    )
                    if age > limit:
                        stale.append(
                            PausedField(
                                field=name, age_seconds=age, reason=f"{name} unread"
                            )
                        )
                except KeyError, TypeError, ValueError:
                    stale.append(
                        PausedField(field=name, reason=f"{name} timestamp unread")
                    )
        if mode != "baseline" or self.data is None:
            return BaselineState(mode=mode, status=self.status, stale=tuple(stale))
        data = self.data
        guide = data.guides.get(self.selected_id)
        round_id = self.snapshot.get("round_id") if self.snapshot else None
        phase = self.snapshot.get("phase", "unknown") if self.snapshot else "unknown"
        warnings = list(data.warnings)

        def entity(id):
            if id not in data.entities:
                raise DataError(f"Guide entity unavailable: {id}")
            item = data.entities[id]
            return EntityDisplay(id=id, name=item.name, icon=item.icon, cost=item.cost)

        def summary(g):
            return GuideSummary(
                id=g.id,
                name=g.id.replace("-", " ").replace("_", " ").title(),
                tier=g.tier,
                units=tuple(entity(id) for id in g.units),
            )

        def canonical(id):
            value = data.entities[id].values.get("canonical_id")
            result = value.value if value else id
            if result not in data.entities:
                raise DataError(f"Canonical unit entity unavailable: {result}")
            return result

        def field(name):
            item = self.snapshot.get("fields", {}).get(name) if self.snapshot else None
            age = None
            if item and "read_at" in item:
                try:
                    age = max(
                        0,
                        (now - datetime.fromisoformat(item["read_at"])).total_seconds(),
                    )
                except ValueError, TypeError:
                    pass
            thresholds = data.tunables.get("field_max_age_seconds")
            thresholds = thresholds.value if thresholds else {}
            limit = (
                thresholds.get(name, 2)
                if isinstance(thresholds, Mapping)
                else float(thresholds)
            )
            if item is None or age is None or age > limit:
                stale.append(
                    PausedField(field=name, age_seconds=age, reason=f"{name} unread")
                )
                return None
            return item.get("value")

        guides = tuple(
            summary(g)
            for g in sorted(
                data.guides.values(), key=lambda g: (TIER_ORDER.get(g.tier, 99), g.id)
            )
        )
        selected = None
        recipes = []
        augments = []
        shop = []
        wisps = []
        hint = None
        voice = None
        if guide:
            selected = GuideDisplay(
                **summary(guide).model_dump(),
                early_layout=tuple(
                    LayoutUnit(
                        entity=entity(id), position=guide.early_positions.get(id)
                    )
                    for id in guide.early_units
                ),
                final_layout=tuple(
                    LayoutUnit(entity=entity(id), position=guide.positions.get(id))
                    for id in guide.units
                ),
                stage_tips=dict(guide.stage_tips),
                stage_plan=tuple(
                    {
                        k: v
                        for k, v in p.items()
                        if k in ("round", "level", "roll_level", "gold_floor")
                    }
                    for p in guide.line
                ),
                carousel=tuple(entity(id) for id in guide.carousel),
                alternatives=guide.alternatives,
            )
            components = field("components")
            counts = Counter(components or ())
            item_sets = dict(guide.early_items)
            for unit_id, items in guide.items.items():
                item_sets[unit_id] = tuple(
                    dict.fromkeys((*item_sets.get(unit_id, ()), *items))
                )
            for unit_id, items in item_sets.items():
                for item_id in items:
                    ingredients = data.value("item_recipes").get(item_id, ())
                    available = counts.copy()
                    parts = []
                    for id in ingredients:
                        held = available[id] > 0
                        available[id] -= 1
                        parts.append(RecipeComponent(entity=entity(id), held=held))
                    recipes.append(
                        ItemRecipe(
                            unit=entity(unit_id),
                            item=entity(item_id),
                            components=tuple(parts),
                        )
                    )
            rows = field("shop")
            guide_units = {canonical(id) for id in (*guide.units, *guide.early_units)}
            for index, row in enumerate(rows or ()):
                if not row or not row.get("unit_id"):
                    continue
                shop.append(
                    ShopHighlight(
                        slot=row.get("slot", index),
                        entity=entity(row["unit_id"]),
                        in_guide=canonical(row["unit_id"]) in guide_units,
                    )
                )
            try:
                level, xp = field("level"), field("xp")
                if level is not None and xp is not None and round_id:
                    hint = self._xp_hint(guide, round_id, level, xp)
            except (KeyError, TypeError, ValueError, DataError) as error:
                stale.append(
                    PausedField(
                        field="xp_plan", reason=f"Guide XP hint unavailable: {error}"
                    )
                )
            if round_id:
                stage = round_id.split("-")[0]
                game_id = str(self.snapshot.get("game_id", ""))
                key = (game_id, stage)
                text = guide.stage_tips.get(stage)
                if (
                    text
                    and game_id
                    and phase == "planning"
                    and self._round_start
                    and key not in self._spoken
                ):
                    voice = StageVoice(
                        id=f"{game_id}:baseline-stage:{stage}", text=text
                    )
                    self._spoken.add(key)
        offered = field("augments") or ()
        offered_ids = {
            row["augment_id"] if isinstance(row, Mapping) else row for row in offered
        }
        offer_index = {
            row["augment_id"] if isinstance(row, Mapping) else row: i
            for i, row in enumerate(offered)
        }
        comp_tiers = (
            data.comp_augment_tiers.get(guide.cluster_id, {})
            if guide and guide.cluster_id
            else {}
        )
        ids = (
            set(guide.augment_tiers if guide else ())
            | set(comp_tiers)
            | set(data.augment_tiers)
            | offered_ids
        )
        for id in sorted(ids):
            augments.append(
                AugmentTier(
                    entity=entity(id),
                    tier=comp_tiers.get(id, data.augment_tiers.get(id)),
                    global_tier=data.augment_tiers.get(id),
                    in_guide=guide is not None and id in guide.augment_tiers,
                    offered=id in offered_ids,
                    offer_index=offer_index.get(id),
                )
            )
        offered_wisp = field("wisp") or {}
        worth_table = data.static.get("wisp_worth")
        for id, rule in data.value("wisps").items():
            if id not in data.entities:
                raise DataError(f"Wisp entity unavailable: {id}")
            worth = worth_table.value.get(id) if worth_table else rule.get("worth")
            if worth is not None and (
                not isinstance(worth, (int, float)) or not isfinite(worth)
            ):
                warnings.append(f"Wisp worth unavailable: {id}")
                worth = None
            wisps.append(
                WispWorth(
                    entity=entity(id),
                    worth=worth,
                    source=worth_table.source
                    if worth_table
                    else data.static["wisps"].source,
                    offered_slot=offered_wisp.get("slot", 4)
                    if offered_wisp.get("wisp_id") == id
                    else None,
                )
            )
        par = ParChance(paused="own board unread")
        board_value, level_value = field("board"), field("level")
        complete = field("inventory_complete")
        if board_value is not None and level_value is not None and round_id:
            try:
                board_field = self.snapshot["fields"]["board"]
                confidence = board_field.get("confidence", 0)
                minimum = data.tunables.get("confidence_medium_min")
                if (
                    complete is not True
                    or minimum is None
                    or confidence < minimum.value
                ):
                    raise DataError("own board incomplete or low confidence")
                if not isinstance(board_value, Mapping) or "units" not in board_value:
                    raise DataError("own board schema unavailable")
                units = []
                for row in board_value["units"]:
                    if row.get("stars") not in (1, 2, 3) or "items" not in row:
                        raise DataError("own board stars or equipped items unread")
                    units.append(
                        OwnUnit(row["unit_id"], row["stars"], tuple(row["items"]))
                    )
                own = OwnBoard(tuple(units), board_value.get("trait_counts"))
                curve = data.tunables.get("opponent_growth_curve")
                own_power = strength(own, level_value, data)
                par_power = growth_curve_lookup(
                    round_id, data, curve=curve.value if curve else None
                )
                probability = win_probability(
                    own_power, par_power, int(round_id.split("-")[0]), data
                )
                if not isfinite(probability):
                    raise DataError("par probability invalid")
                uncertainty = any(
                    value.source in ("default", "carried")
                    for name, value in data.tunables.items()
                    if name
                    in (
                        "unit_weight",
                        "trait_weight",
                        "item_weight",
                        "fight_scale",
                        "win_scale_by_stage",
                    )
                )
                par = ParChance(probability=probability, uncertain=uncertainty)
            except (KeyError, TypeError, ValueError, DataError) as error:
                par = ParChance(paused=str(error))
        content = BaselineContent(
            patch=data.patch,
            snapshot_id=data.snapshot_id,
            round_id=round_id,
            guides=guides,
            selected=selected,
            xp_hint=hint,
            par=par,
            shop=tuple(shop),
            recipes=tuple(recipes),
            augments=tuple(augments),
            wisps=tuple(wisps),
            faced=self.faced,
            warnings=tuple(warnings),
            phase=phase,
            anchors=self.anchors,
            overlay_bounds=self.overlay_bounds,
            overlay_allowed=self.overlay_allowed,
        )
        return BaselineState(
            mode=mode,
            status=self.status,
            stale=tuple({row.field: row for row in stale}.values()),
            content=content,
            voice=voice,
        )

    def _xp_hint(
        self, guide: Guide, round_id: str, level: int, xp: float
    ) -> XpHint:
        data = self.data
        order = tuple(data.value("round_order"))
        current = order.index(round_id)
        candidates = [
            p
            for p in guide.line
            if p.get("round") in order
            and order.index(p["round"]) >= current
            and "level" in p
        ]
        if not candidates:
            raise DataError("Guide has no explicit future level target")
        target = min(candidates, key=lambda p: order.index(p["round"]))
        target_level = int(target["level"])
        if (
            not isinstance(level, int)
            or not 1 <= level <= 10
            or not isinstance(xp, (int, float))
            or xp < 0
        ):
            raise DataError("level or XP invalid")
        flags = data.value("rules_flags")
        rounds = order[current + 1 : order.index(target["round"]) + 1]
        passive = int(flags["passive_xp"]) * len(rounds)
        needed = (
            sum(data.value("xp_table")[str(i)] for i in range(level, target_level))
            - xp
            - passive
        )
        buys = max(0, ceil(needed / flags["xp_buy_amount"]))
        gold = buys * int(flags["xp_buy_cost"])
        text = f"Guide: {target_level} at {target['round']} · {buys} XP buys ({gold} gold) short"
        return XpHint(
            target_level=target_level,
            target_round=target["round"],
            buys=buys,
            gold=gold,
            passive_xp=passive,
            text=text,
        )
