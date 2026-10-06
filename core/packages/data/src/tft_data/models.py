"""Public immutable data contracts. Source payloads are never Engine inputs."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal, Mapping

SourceTag = Literal['cdragon', 'ddragon', 'patch-notes', 'carried', 'default', 'owner']

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
    citation: str = ''
    family: str = ''
    def __post_init__(self):
        if self.source not in {'cdragon', 'ddragon', 'patch-notes', 'carried', 'default', 'owner'}:
            raise DataError(f'Unknown source tag: {self.source}')
        if self.source == 'patch-notes' and not self.citation:
            raise DataError('Patch-note values require a citation')
        object.__setattr__(self, 'value', freeze(self.value))


@dataclass(frozen=True)
class Entity:
    id: str
    kind: str
    name: str
    cost: int = 0
    traits: tuple[str, ...] = ()
    text: str = ''
    icon: str = ''
    values: Mapping[str, TaggedValue] = field(default_factory=dict)
    threat_tags: tuple[str, ...] = ()
    def __post_init__(self):
        object.__setattr__(self, 'values', freeze(self.values))


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
    source: str = 'tftacademy'
    def __post_init__(self):
        for key in ('items', 'positions', 'stage_tips', 'augment_tiers', 'line'):
            object.__setattr__(self, key, freeze(getattr(self, key)))


@dataclass(frozen=True)
class SourceState:
    name: str
    patch: str
    updated_at: datetime
    fetched_at: datetime
    kind: str


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
    def __post_init__(self):
        for key in ('static', 'tunables', 'entities', 'guides', 'sources'):
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
