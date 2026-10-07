"""Immutable, JSON-safe contracts shared by capture, advice and replay."""
from __future__ import annotations
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from typing import Any, Literal, Mapping
from tft_data.models import freeze

Mode = Literal['baseline', 'live', 'silent', 'review']


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_encode(v) for v in value]
    return value


@dataclass(frozen=True)
class Unit:
    unit_id: str
    stars: int = 1
    items: tuple[str, ...] = ()
    position: int | None = None
    def __post_init__(self):
        if self.stars not in (1, 2, 3):
            raise ValueError('Unit stars must be 1, 2 or 3')
        object.__setattr__(self, 'items', tuple(self.items))
    @classmethod
    def from_dict(cls, value):
        return cls(value['unit_id'], value.get('stars', 1), tuple(value.get('items', ())), value.get('position'))


@dataclass(frozen=True)
class Board:
    units: tuple[Unit, ...] = ()
    bench: tuple[Unit, ...] = ()
    trait_counts: Mapping[str, int] | None = None
    def __post_init__(self):
        object.__setattr__(self, 'units', tuple(self.units))
        object.__setattr__(self, 'bench', tuple(self.bench))
        if self.trait_counts is not None:
            object.__setattr__(self, 'trait_counts', freeze(self.trait_counts))
    @classmethod
    def from_dict(cls, value):
        return cls(tuple(Unit.from_dict(u) for u in value.get('units', ())), tuple(Unit.from_dict(u) for u in value.get('bench', ())), value.get('trait_counts'))
    def to_dict(self):
        return _encode(self)


@dataclass(frozen=True)
class FieldValue:
    value: Any
    read_at: datetime
    source: str
    confidence: float = 1.0
    def __post_init__(self):
        if self.read_at.tzinfo is None:
            raise ValueError('Field timestamps require a timezone')
        if not 0 <= self.confidence <= 1:
            raise ValueError('Field confidence must be between 0 and 1')
        object.__setattr__(self, 'value', freeze(self.value))
    def age_seconds(self, now: datetime) -> float:
        return max(0.0, (now - self.read_at).total_seconds())


@dataclass(frozen=True)
class GameSnapshot:
    game_id: str
    round_id: str
    captured_at: datetime
    fields: Mapping[str, FieldValue] = field(default_factory=dict)
    snapshot_id: str = ''
    def __post_init__(self):
        if self.captured_at.tzinfo is None:
            raise ValueError('Snapshot timestamps require a timezone')
        object.__setattr__(self, 'fields', freeze(self.fields))
    def field(self, name: str, *, now: datetime | None = None, max_age_seconds: float = 2) -> Any | None:
        value = self.fields.get(name)
        if value is None or value.age_seconds(now or self.captured_at) > max_age_seconds:
            return None
        return value.value
    def to_dict(self):
        return _encode(self)
    @classmethod
    def from_dict(cls, value):
        decoded = {}
        for name, item in value.get('fields', {}).items():
            payload = item['value']
            if name == 'board' and isinstance(payload, dict):
                payload = Board.from_dict(payload)
            elif name == 'bench' and isinstance(payload, list):
                payload = tuple(Unit.from_dict(u) for u in payload)
            decoded[name] = FieldValue(payload, datetime.fromisoformat(item['read_at']), item['source'], item.get('confidence', 1.0))
        return cls(value['game_id'], value['round_id'], datetime.fromisoformat(value['captured_at']), decoded, value.get('snapshot_id', ''))


@dataclass(frozen=True)
class TraitSighting:
    opponent_id: str
    round_id: str
    level: int
    traits: Mapping[str, int]
    hidden_traits: int = 0
    def __post_init__(self):
        if self.level < 1 or self.hidden_traits < 0 or any(v < 1 for v in self.traits.values()):
            raise ValueError('Invalid trait sighting')
        object.__setattr__(self, 'traits', freeze(self.traits))
    def to_dict(self):
        return _encode(self)
    @classmethod
    def from_dict(cls, value):
        return cls(**value)


@dataclass(frozen=True)
class GameHistory:
    snapshots: tuple[GameSnapshot, ...] = ()
    sightings: tuple[TraitSighting, ...] = ()
    def __post_init__(self):
        object.__setattr__(self, 'snapshots', tuple(self.snapshots))
        object.__setattr__(self, 'sightings', tuple(self.sightings))
    def to_dict(self):
        return _encode(self)
    @classmethod
    def from_dict(cls, value):
        return cls(tuple(GameSnapshot.from_dict(v) for v in value.get('snapshots', ())), tuple(TraitSighting.from_dict(v) for v in value.get('sightings', ())))


@dataclass(frozen=True)
class ScoredOption:
    option_id: str
    action: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    expected_placement: float | None = None
    standard_error: float | None = None
    reason: str = ''
    def __post_init__(self):
        object.__setattr__(self, 'payload', freeze(self.payload))
    def to_dict(self):
        return _encode(self)
    @classmethod
    def from_dict(cls, value):
        return cls(**value)


@dataclass(frozen=True)
class Advice:
    decision: str
    action: str
    urgency: Literal['act_this_phase', 'soon', 'information']
    confidence: float
    reason: str
    numbers: Mapping[str, float | int | str] = field(default_factory=dict)
    validity: tuple[str, ...] = ()
    placement_impact: float = 0.0
    decision_id: str = ''
    option_id: str = ''
    payload: Mapping[str, Any] = field(default_factory=dict)
    options: tuple[ScoredOption, ...] = ()
    anchors: Mapping[str, Any] = field(default_factory=dict)
    validity_state: Mapping[str, Any] = field(default_factory=dict)
    def __post_init__(self):
        if self.urgency not in ('act_this_phase', 'soon', 'information') or not 0 <= self.confidence <= 1:
            raise ValueError('Invalid advice urgency or confidence')
        object.__setattr__(self, 'numbers', freeze(self.numbers))
        object.__setattr__(self, 'validity', tuple(self.validity))
        object.__setattr__(self, 'options', tuple(self.options))
        for name in ('payload', 'anchors', 'validity_state'):
            object.__setattr__(self, name, freeze(getattr(self, name)))
    def to_dict(self):
        return _encode(self)
    @classmethod
    def from_dict(cls, value):
        value = dict(value)
        value['options'] = tuple(ScoredOption.from_dict(v) for v in value.get('options', ()))
        return cls(**value)


def rank_advice(items):
    priority = {'act_this_phase': 0, 'soon': 1, 'information': 2}
    return tuple(sorted(items, key=lambda a: (priority[a.urgency], -a.placement_impact, a.decision, a.action)))
