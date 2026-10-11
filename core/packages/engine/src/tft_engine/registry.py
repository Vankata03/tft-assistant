"""Explicit deterministic decision hooks; callers can pass a different tuple for review."""
from dataclasses import dataclass, field
from typing import Callable, Mapping
from tft_data.models import freeze

@dataclass(frozen=True)
class FitTerm:
    delta: float
    reason: str
    numbers: Mapping = field(default_factory=dict)
    confidence: float = 1.0
    def __post_init__(self):
        object.__setattr__(self,'numbers',freeze(self.numbers))

@dataclass(frozen=True)
class DomainHook:
    name: str
    required_fields: tuple[str,...]
    fit: Callable | None = None
    advice: Callable | None = None
    fit_required_fields: tuple[str,...] = ()
    advice_phases: tuple[str,...] = ('planning','roll_down')


def default_hooks():
    return ()
