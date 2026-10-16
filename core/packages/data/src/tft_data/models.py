"""Public immutable data contracts. Source payloads are never Engine inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal

SourceTag = Literal["cdragon", "ddragon", "patch-notes", "carried", "default", "owner", "public-statistics"]


class DataError(ValueError):
    """Invalid or unavailable data; callers retain their last good snapshot."""


def freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): freeze(v) for k, v in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(freeze(v) for v in value)
    return value


def plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [plain(v) for v in value]
    return value


@dataclass(frozen=True)
class TaggedValue:
    value: Any
    source: SourceTag
    citation: str = ""
    family: str = ""

    def __post_init__(self):
        if self.source not in {
            "cdragon",
            "ddragon",
            "patch-notes",
            "carried",
            "default",
            "owner",
            "public-statistics",
        }:
            raise DataError(f"Unknown source tag: {self.source}")
        if self.source == "patch-notes" and not self.citation:
            raise DataError("Patch-note values require a citation")
        object.__setattr__(self, "value", freeze(self.value))


@dataclass(frozen=True)
class Entity:
    id: str
    kind: str
    name: str
    cost: int = 0
    traits: tuple[str, ...] = ()
    text: str = ""
    icon: str = ""
    values: Mapping[str, TaggedValue] = field(default_factory=dict)
    threat_tags: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "values", freeze(self.values))
        object.__setattr__(self, "traits", tuple(self.traits))
        object.__setattr__(self, "threat_tags", tuple(self.threat_tags))


@dataclass(frozen=True)
class Statistic:
    entity_id: str
    kind: str
    average_placement: float
    sample_count: int
    patch: str
    source: str
    stale: bool = False
    changed: bool = False
    unit_star: int | None = None
    item_id: str | None = None
    comp_id: str | None = None
    variance: float | None = None
    top4_rate: float | None = None
    play_rate: float | None = None
    breakpoint: int | None = None
    positioning: tuple[float, ...] = ()
    pick_stage: int | None = None

    def __post_init__(self):
        import math

        if self.pick_stage is not None and (
            not isinstance(self.pick_stage, int)
            or isinstance(self.pick_stage, bool)
            or self.pick_stage not in (1, 2, 3)
        ):
            raise DataError("Statistic pick_stage must be canonical 1, 2 or 3")

        if (
            not isinstance(self.sample_count, int)
            or isinstance(self.sample_count, bool)
            or self.sample_count < 0
        ):
            raise DataError("Statistic sample_count must be a nonnegative integer")
        if (
            not math.isfinite(self.average_placement)
            or not 1 <= self.average_placement <= 8
        ):
            raise DataError("Statistic average_placement must be in [1,8]")
        for rate in (self.top4_rate, self.play_rate):
            if rate is not None and (not math.isfinite(rate) or not 0 <= rate <= 1):
                raise DataError("Statistic rates must be in [0,1]")
        if self.positioning and (
            len(self.positioning) != 28
            or any(not math.isfinite(v) or v < 0 for v in self.positioning)
        ):
            raise DataError("Positioning requires 28 nonnegative cell weights")
        object.__setattr__(self, "positioning", tuple(self.positioning))


@dataclass(frozen=True)
class Guide:
    id: str
    tier: str
    units: tuple[str, ...]
    early_units: tuple[str, ...] = ()
    carry_ids: tuple[str, ...] = ()
    items: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    positions: Mapping[str, int] = field(default_factory=dict)
    stage_tips: Mapping[str, str] = field(default_factory=dict)
    augment_tiers: Mapping[str, str] = field(default_factory=dict)
    carousel: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    line: tuple[Mapping[str, Any], ...] = ()
    source: str = "tftacademy"
    key_ids: tuple[str, ...] = ()
    early_items: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    alternative_builds: tuple[Mapping[str, Any], ...] = ()
    cluster_id: str | None = None
    early_positions: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self):
        for key in (
            "units",
            "early_units",
            "carry_ids",
            "carousel",
            "alternatives",
            "key_ids",
        ):
            object.__setattr__(self, key, tuple(getattr(self, key)))
        for key in (
            "items",
            "early_items",
            "early_positions",
            "alternative_builds",
            "positions",
            "stage_tips",
            "augment_tiers",
            "line",
        ):
            object.__setattr__(self, key, freeze(getattr(self, key)))


@dataclass(frozen=True)
class SourceState:
    name: str
    patch: str | None
    updated_at: datetime
    fetched_at: datetime
    kind: str
    filters: Mapping[str, Any] = field(default_factory=dict)
    identity: Mapping[str, Any] = field(default_factory=dict)
    publication: Mapping[str, Any] = field(default_factory=dict)
    donor_hint: Mapping[str, Any] = field(default_factory=dict)
    qualified: bool = True
    qualification_reasons: tuple[str, ...] = ()
    last_attempt: Mapping[str, Any] = field(default_factory=dict)
    cohort: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for name in (
            "filters",
            "identity",
            "publication",
            "donor_hint",
            "last_attempt",
            "cohort",
        ):
            object.__setattr__(self, name, freeze(getattr(self, name)))
        object.__setattr__(
            self, "qualification_reasons", tuple(self.qualification_reasons)
        )


@dataclass(frozen=True)
class DataSnapshot:
    snapshot_id: str
    patch: str
    set_number: int
    static: Mapping[str, TaggedValue]
    tunables: Mapping[str, TaggedValue]
    entities: Mapping[str, Entity] = field(default_factory=dict)
    statistics: tuple[Statistic, ...] = ()
    guides: Mapping[str, Guide] = field(default_factory=dict)
    sources: Mapping[str, SourceState] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    changed_ids: tuple[str, ...] = ()
    lobby_top4_rate: float | None = None
    positioning: Mapping[str, tuple[float, ...]] = field(default_factory=dict)
    augment_tiers: Mapping[str, str] = field(default_factory=dict)
    comp_augment_tiers: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def __post_init__(self):
        for key in ("statistics", "warnings", "changed_ids"):
            object.__setattr__(self, key, tuple(getattr(self, key)))
        for key in (
            "static",
            "tunables",
            "entities",
            "guides",
            "sources",
            "positioning",
            "augment_tiers",
            "comp_augment_tiers",
        ):
            object.__setattr__(self, key, freeze(getattr(self, key)))

    def value(self, name: str) -> Any:
        return self.static[name].value

    def tunable(self, name: str) -> Any:
        return self.tunables[name].value

    @property
    def names(self) -> Mapping[str, str]:
        return freeze({id: e.name for id, e in self.entities.items()})

    @property
    def icons(self) -> Mapping[str, str]:
        return freeze({id: e.icon for id, e in self.entities.items() if e.icon})


@dataclass(frozen=True)
class RefreshResult:
    snapshot: DataSnapshot | None
    changed: bool = False
    warnings: tuple[str, ...] = ()
    deferred: bool = False
    error: str | None = None
