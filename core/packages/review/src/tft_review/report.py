"""Versioned private report and primitive surface summary contracts."""
from collections.abc import Mapping
from dataclasses import dataclass, field

from .contracts import frozen_json, json_value
from .identity import digest


@dataclass(frozen=True)
class ReviewReport:
    game_id: str
    summary: Mapping
    timeline: tuple[Mapping, ...]
    moments: tuple[Mapping, ...]
    evidence: Mapping
    schema_version: int = 1
    lines: tuple[Mapping, ...] = ()
    plan_timeline: tuple[Mapping, ...] = ()
    fights: tuple[Mapping, ...] = ()
    positioning: tuple[Mapping, ...] = ()
    debug: Mapping = field(default_factory=dict)
    surface: Mapping = field(default_factory=dict)

    def __post_init__(self):
        if self.schema_version != 1:
            raise ValueError('Unsupported review report schema')
        for name in ('summary', 'evidence', 'debug', 'surface'):
            object.__setattr__(self, name, frozen_json(getattr(self, name)))
        for name in ('timeline', 'moments', 'lines', 'plan_timeline', 'fights', 'positioning'):
            object.__setattr__(self, name, tuple(frozen_json(row) for row in getattr(self, name)))

    @property
    def report_id(self):
        return digest(self.to_dict())

    def to_dict(self):
        return json_value(self)

    @classmethod
    def from_dict(cls, value):
        return cls(**value)
