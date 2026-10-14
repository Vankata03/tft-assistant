"""Finite, immutable aggregate harness output; private examples are permission-filtered."""
from dataclasses import dataclass, field
from collections.abc import Mapping
from tft_review.contracts import frozen_json, json_value


@dataclass(frozen=True)
class HarnessReport:
    metrics: Mapping
    gates: Mapping
    counts: Mapping
    examples: tuple[Mapping, ...] = ()
    manifest: tuple[Mapping, ...] = ()
    provenance: Mapping = field(default_factory=dict)
    schema_version: int = 1

    def __post_init__(self):
        for name in ('metrics', 'gates', 'counts', 'provenance'):
            object.__setattr__(self, name, frozen_json(getattr(self, name)))
        for name in ('examples', 'manifest'):
            object.__setattr__(self, name, tuple(frozen_json(row) for row in getattr(self, name)))

    def to_dict(self):
        return json_value(self)
