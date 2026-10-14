"""Trait-event likelihood from an explicitly declared whole-board joint law."""
from dataclasses import dataclass
from math import fsum, isfinite, log
from collections.abc import Mapping

from tft_data.models import DataError, DataSnapshot, TaggedValue, freeze
from tft_data.capacity import integral

from .capacity import CapacityEvidence, CapacityModel
from .models import Board, TraitSighting, Unit
from .trait_forms import unit_trait_variants


@dataclass(frozen=True)
class JointHypothesis:
    """A complete weighted board outcome, including declared active forms/items."""
    board: Board
    weight: float
    capacity: CapacityEvidence = CapacityEvidence()
    forms: tuple[Mapping[str, int], ...] | None = None

    def __post_init__(self):
        if not isinstance(self.board, Board) or not isinstance(self.capacity, CapacityEvidence):
            raise DataError('Joint support requires immutable Board and CapacityEvidence values')
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)) or not isfinite(self.weight) or self.weight < 0:
            raise DataError('Joint support requires finite nonnegative weights')
        if self.forms is not None:
            object.__setattr__(self, 'forms', tuple(freeze(form) for form in self.forms))


@dataclass(frozen=True)
class JointSightingLaw:
    """Immutable supplied support, bound to one snapshot/player/round/level.

    Source and citation identify the declaration; they do not qualify a current
    production model. The producer must supply support before conditioning on
    the target trait event. No unit, form or emblem law is invented here.
    """
    snapshot_id: str
    opponent_id: str
    round_id: str
    level: int
    source: str
    citation: str
    hypotheses: tuple[JointHypothesis, ...]

    def __post_init__(self):
        integral(self.level, 'joint law level', 1)
        object.__setattr__(self, 'hypotheses', tuple(self.hypotheses))
        for name in ('snapshot_id', 'opponent_id', 'round_id', 'source', 'citation'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise DataError(f'Joint law requires {name}')
        if not self.hypotheses or not all(isinstance(item, JointHypothesis) for item in self.hypotheses) or not any(item.weight > 0 for item in self.hypotheses):
            raise DataError('Joint law requires positive declared support mass')


@dataclass(frozen=True)
class JointSightingPrediction:
    """A joint event score; log_probability retains positive underflow mass.

    With an available law, probability zero and log_probability None mean an
    impossible event. A finite log score with probability zero means float
    underflow. Missing laws have an explicit unavailable reason.
    """
    probability: float | None
    reason: str | None
    source: str | None
    log_probability: float | None = None


class _ResolvedCapacity(CapacityModel):
    """Use certified joint forms with the existing slot/inventory legality rules."""
    def __init__(self, data, counts):
        super().__init__(data)
        self.resolved_counts = freeze(counts)

    def counts(self, board):
        if board.trait_counts is not None and dict(board.trait_counts) != dict(self.resolved_counts):
            raise DataError('Observed joint trait counts conflict with certified grants')
        return self.resolved_counts


def _breakpoint(trait, data):
    entity = data.entities.get(trait)
    tagged = entity.values.get('breakpoints') if entity else None
    if not entity or entity.kind != 'trait' or not isinstance(tagged, TaggedValue) or not isinstance(tagged.value, (tuple, list)):
        raise DataError(f'Joint support trait breakpoint unavailable: {trait}')
    points = [integral(point, 'trait breakpoint', 1) for point in tagged.value if point is not None]
    if not points:
        raise DataError(f'Joint support trait breakpoint unavailable: {trait}')
    return min(points)


def _add_grants(counts, grants, data, *, minimum=0):
    if not isinstance(grants, Mapping):
        raise DataError('Joint support requires certified integral trait grants')
    for trait, number in grants.items():
        integral(number, 'joint trait grant', minimum)
        _breakpoint(trait, data)
        if number:
            counts[trait] = counts.get(trait, 0) + number


def predict_joint_sighting(sighting: TraitSighting, data: DataSnapshot,
    law: JointSightingLaw | None) -> JointSightingPrediction:
    """Normalize supplied legal support and score the complete trait event.

    Level is bound by the supplied law. If present, observed team-slot budget
    is part of the scored event. Hidden traits must have positive counts below
    their first breakpoint; omitted active traits cannot become hidden mass.
    """
    if law is None:
        return JointSightingPrediction(None, 'joint_sighting_law_unavailable', None)
    if (law.snapshot_id, law.opponent_id, law.round_id, law.level) != (
        data.snapshot_id, sighting.opponent_id, sighting.round_id, sighting.level):
        raise DataError('Joint law does not match the snapshot and sighting context')
    for trait in sighting.traits:
        _breakpoint(trait, data)
    scale = max(hypothesis.weight for hypothesis in law.hypotheses)
    matching = []
    for hypothesis in law.hypotheses:
        counts = {}
        counted = {}
        for unit in hypothesis.board.units + hypothesis.board.bench:
            entity = data.entities.get(unit.unit_id) if isinstance(unit, Unit) else None
            if not entity or entity.kind not in ('unit', 'unit_form'):
                raise DataError('Joint support contains an unknown unit')
        for index, unit in enumerate(hypothesis.board.units):
            variants = unit_trait_variants(unit.unit_id, data)
            if hypothesis.forms is None:
                if len(variants) != 1:
                    raise DataError('Joint support requires an explicit active form')
                form = variants[0]
            else:
                if len(hypothesis.forms) != len(hypothesis.board.units):
                    raise DataError('Joint support active forms must match physical units')
                form = hypothesis.forms[index]
                if form not in variants:
                    raise DataError('Joint support active form lacks a static certificate')
            entity = data.entities[unit.unit_id]
            pool = entity.values.get('pool_id') or entity.values.get('canonical_id')
            identity = pool.value if pool else unit.unit_id
            if not isinstance(identity, str):
                raise DataError('Joint support has an invalid unit pool identity')
            state = (unit.unit_id, dict(form))
            if identity in counted and counted[identity] != state:
                raise DataError('Joint support contains conflicting active forms')
            if identity not in counted:
                _add_grants(counts, form, data)
                counted[identity] = state
            for item_id in unit.items:
                item = data.entities.get(item_id)
                grants = item.values.get('trait_grants') if item else None
                if not item or item.kind != 'item' or not isinstance(grants, TaggedValue) or not isinstance(grants.value, Mapping):
                    raise DataError('Joint support item trait-grant certificate unavailable')
                _add_grants(counts, grants.value, data, minimum=1)
        state = _ResolvedCapacity(data, counts).check(hypothesis.board, sighting.level, hypothesis.capacity, check_observed=True)
        outside = {trait: number for trait, number in counts.items() if trait not in sighting.traits and number}
        hidden = all(number < _breakpoint(trait, data)
            for trait, number in outside.items())
        if (sighting.team_slot_budget is None or sighting.team_slot_budget == state.maximum_slots) and all(counts.get(trait, 0) == number for trait, number in sighting.traits.items()) and len(outside) == sighting.hidden_traits and hidden:
            matching.append(hypothesis.weight)
    normalizer = fsum(hypothesis.weight / scale for hypothesis in law.hypotheses)
    probability = fsum(weight / scale for weight in matching) / normalizer
    event_scale = max(matching, default=0)
    log_probability = min(0.0, (log(event_scale) - log(scale))
        + (log(fsum(weight / event_scale for weight in matching)) - log(normalizer))) if event_scale > 0 else None
    return JointSightingPrediction(probability, None, law.source, log_probability)
