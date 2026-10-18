"""Immutable, JSON-safe contracts shared by capture, advice and replay."""
from __future__ import annotations
from dataclasses import dataclass, field, fields, is_dataclass
from collections.abc import Sequence
from operator import index as sequence_index
from datetime import datetime
import json
import weakref
from types import MappingProxyType
from typing import Any, Literal, Mapping
from tft_data.models import freeze

Mode = Literal['baseline', 'live', 'silent', 'review']


_SCALARS = frozenset((str, int, float, bool, type(None)))
_DATACLASS_FIELDS: dict[type, tuple[str, ...]] = {}


def _encode(value: Any) -> Any:
    # Exact builtin types and already-seen dataclasses take the same branch the
    # general checks below would take; subclasses still use those checks.
    kind = type(value)
    if kind in _SCALARS:
        return value
    if kind is tuple or kind is list:
        return [_encode(v) for v in value]
    if kind is dict or kind is MappingProxyType:
        return {k: _encode(v) for k, v in value.items()}
    names = _DATACLASS_FIELDS.get(kind)
    if names is not None:
        return {name: _encode(getattr(value, name)) for name in names}
    if isinstance(value, GameHistory):
        return {'snapshots': _encode(value.snapshots), 'sightings': _encode(value.sightings)}
    if isinstance(value, HistoryWindow):
        return [_encode(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        names = tuple(f.name for f in fields(value))
        if not isinstance(value, type):
            _DATACLASS_FIELDS[kind] = names
        return {name: _encode(getattr(value, name)) for name in names}
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
    read_at: datetime | None = None
    team_slot_budget: int | None = None
    def __post_init__(self):
        if self.level < 1 or self.hidden_traits < 0 or any(v < 1 for v in self.traits.values()):
            raise ValueError('Invalid trait sighting')
        if self.team_slot_budget is not None and (isinstance(self.team_slot_budget,bool) or not isinstance(self.team_slot_budget,int) or self.team_slot_budget<1):
            raise ValueError('Invalid observed opponent team slot budget')
        object.__setattr__(self, 'traits', freeze(self.traits))
    def to_dict(self):
        return _encode(self)
    @classmethod
    def from_dict(cls, value):
        value=dict(value)
        if isinstance(value.get('read_at'),str):
            value['read_at']=datetime.fromisoformat(value['read_at'])
        return cls(**value)


class HistoryWindow(Sequence):
    """Immutable range over one tuple, without copying each historical prefix."""
    __slots__ = ('_rows', '_start', '_stop')

    def __init__(self, rows, start=0, stop=None):
        rows = rows if isinstance(rows, tuple) else tuple(rows)
        start, stop, _ = slice(start, stop).indices(len(rows))
        object.__setattr__(self, '_rows', rows)
        object.__setattr__(self, '_start', start)
        object.__setattr__(self, '_stop', max(start, stop))

    def __setattr__(self, name, value):
        raise AttributeError('Historical windows are immutable')

    def __len__(self):
        return self._stop-self._start

    def __getitem__(self, key):
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            if step == 1:
                return HistoryWindow(self._rows, self._start+start, self._start+max(start, stop))
            return tuple(self[index] for index in range(start, stop, step))
        key = sequence_index(key)
        if key < 0:
            key += len(self)
        if key < 0 or key >= len(self):
            raise IndexError('Historical window index out of range')
        return self._rows[self._start+key]

    def __iter__(self):
        for index in range(self._start, self._stop):
            yield self._rows[index]

    def __eq__(self, other):
        if not isinstance(other, Sequence) or isinstance(other, (str, bytes, bytearray)):
            return NotImplemented
        return len(self) == len(other) and all(left == right for left, right in zip(self, other))


@dataclass(frozen=True)
class GameHistory:
    snapshots: tuple[GameSnapshot, ...] | HistoryWindow = ()
    sightings: tuple[TraitSighting, ...] | HistoryWindow = ()
    source_reference: Mapping | None = field(default=None, compare=False, repr=False)
    def __post_init__(self):
        object.__setattr__(self, 'snapshots', self.snapshots if isinstance(self.snapshots, HistoryWindow) else tuple(self.snapshots))
        object.__setattr__(self, 'sightings', self.sightings if isinstance(self.sightings, HistoryWindow) else tuple(self.sightings))
        if self.source_reference is not None:
            object.__setattr__(self, 'source_reference', freeze(self.source_reference))
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


_ELEMENT_ENCODINGS: dict[tuple[int, str], tuple[weakref.ref, Any]] = {}
_ELEMENT_ENCODERS = {
    'json': lambda value: json.dumps(_encode(value), sort_keys=True, separators=(',', ':'), allow_nan=False),
    'frozen': lambda value: freeze(_encode(value)),
}


def _element_encoding(value, kind):
    """Exact encoding of one history element, retained while the element lives.

    Snapshots and sightings freeze their contents, so one object always encodes
    identically. Other element types are encoded on every call.
    """
    if type(value) not in (GameSnapshot, TraitSighting):
        return _ELEMENT_ENCODERS[kind](value)
    key = (id(value), kind)
    entry = _ELEMENT_ENCODINGS.get(key)
    if entry is not None and entry[0]() is value:
        return entry[1]
    result = _ELEMENT_ENCODERS[kind](value)

    def forget(reference, key=key):
        current = _ELEMENT_ENCODINGS.get(key)
        if current is not None and current[0] is reference:
            del _ELEMENT_ENCODINGS[key]
    _ELEMENT_ENCODINGS[key] = (weakref.ref(value, forget), result)
    return result


def history_json(history: GameHistory) -> str:
    """Compact key-sorted JSON of ``_encode(history)``, reusing element encodings."""
    if type(history) is not GameHistory:
        return json.dumps(_encode(history), sort_keys=True, separators=(',', ':'), allow_nan=False)
    sightings = ','.join(_element_encoding(value, 'json') for value in history.sightings)
    snapshots = ','.join(_element_encoding(value, 'json') for value in history.snapshots)
    return '{"sightings":[' + sightings + '],"snapshots":[' + snapshots + ']}'


def frozen_history(history: GameHistory):
    """``freeze(_encode(history))``, reusing element encodings."""
    if type(history) is not GameHistory:
        return freeze(_encode(history))
    return MappingProxyType({
        'snapshots': tuple(_element_encoding(value, 'frozen') for value in history.snapshots),
        'sightings': tuple(_element_encoding(value, 'frozen') for value in history.sightings)})
