"""Absolute board power and cheap combat projections over an immutable data snapshot."""
from __future__ import annotations
from dataclasses import dataclass
from math import exp, log
from typing import Mapping
from tft_data.models import DataError, DataSnapshot
from .models import Board


@dataclass(frozen=True)
class PowerEstimate:
    power: float
    confidence: float
    unit_term: float
    trait_term: float
    item_term: float
    warnings: tuple[str, ...] = ()


def sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + exp(-value))
    e = exp(value)
    return e / (1 + e)


def logit(rate: float) -> float:
    if not 0 < rate < 1:
        raise DataError('Top-4 rates must be strictly between 0 and 1')
    return log(rate / (1 - rate))


def tunable(data, name):
    try:
        return data.tunable(name)
    except KeyError:
        raise DataError(f'Missing Engine tunable: {name}') from None


def static(data, name):
    try:
        return data.value(name)
    except KeyError:
        raise DataError(f'Missing Engine static field: {name}') from None


def keyed(table, key):
    return table.get(str(key), table.get(key)) if isinstance(table, Mapping) else None


def stage_tunable(data, name, round_id):
    value=tunable(data,name)
    if isinstance(value,Mapping):
        stage=str(round_id).split('-')[0]
        value=keyed(value,stage)
        if value is None:
            raise DataError(f'Missing {name} for stage {stage}')
    return float(value)


def lobby_rate(data):
    rate = getattr(data, 'lobby_top4_rate', None)
    if rate is None:
        rate = static(data, 'lobby_top4_rate')
    return float(rate)


def unit_power(unit_id, stars, data):
    entity = data.entities[unit_id]
    baseline = keyed(keyed(tunable(data, 'cost_star_baseline'), entity.cost), stars)
    if baseline is None:
        raise DataError(f'Missing cost-star baseline: cost {entity.cost}, stars {stars}')
    baseline = float(baseline)
    pool=entity.values.get('canonical_id') or entity.values.get('pool_id')
    statistic_id=pool.value if pool else unit_id
    stats = [s for s in data.statistics if s.entity_id in (unit_id,statistic_id) and s.unit_star == stars and getattr(s, 'top4_rate', None) is not None]
    stats.sort(key=lambda s: (s.entity_id!=unit_id,s.source != 'tactics.tools', s.stale, s.changed))
    statistic = stats[0] if stats else None
    rate = getattr(statistic, 'top4_rate', None)
    samples = statistic.sample_count if statistic else None
    if rate is None:
        tagged = entity.values.get(f'top4_rate_{stars}')
        rate = tagged.value if tagged else None
        count = entity.values.get(f'sample_count_{stars}')
        samples = count.value if count else None
    if rate is None or samples is None:
        return baseline, float(tunable(data, 'confidence_medium_min')), (f'{unit_id}/{stars}: cost-star prior; top-4 split unavailable',)
    prior = float(tunable(data, 'unit_prior_strength'))
    if samples < 0 or prior < 0:
        raise DataError('Sample counts and prior strength must be nonnegative')
    confidence = samples / (samples + prior) if samples + prior else 0.0
    warnings = []

    if statistic and (statistic.stale or statistic.changed):
        confidence *= float(tunable(data, 'confidence_medium_min'))
        warnings.append(f'{unit_id}/{stars}: stale or changed statistics')
    if not 0 <= float(rate) <= 1:
        raise DataError('Top-4 rates must be between 0 and 1')
    lobby = lobby_rate(data)
    prior_rate = sigmoid(logit(lobby) + baseline)
    posterior_rate = confidence * float(rate) + (1 - confidence) * prior_rate
    if not 0 < posterior_rate < 1:
        raise DataError('Endpoint top-4 statistics require positive prior strength')
    value = logit(posterior_rate) - logit(lobby)
    return value, confidence, tuple(warnings)


def trait_term(counts, data):
    total = 0.0
    confidence = 1.0
    warnings = []
    for trait, count in counts.items():
        entity = data.entities.get(trait)
        if entity is None or 'breakpoints' not in entity.values:
            raise DataError(f'Missing trait breakpoints: {trait}')
        active = [int(b) for b in entity.values['breakpoints'].value if count >= int(b)]
        if not active:
            continue
        breakpoint = max(active)
        statistics = [s for s in data.statistics if s.entity_id == trait and getattr(s,'breakpoint',None) == breakpoint and getattr(s,'top4_rate',None) is not None]
        statistics.sort(key=lambda s: (s.source != 'tactics.tools', s.stale, s.changed))
        stat = statistics[0] if statistics else None
        tagged = entity.values.get(f'top4_rate_{breakpoint}')
        rate = getattr(stat, 'top4_rate', None) if stat else (tagged.value if tagged else None)
        if rate is None:
            confidence = min(confidence, float(tunable(data, 'confidence_medium_min')))
            warnings.append(f'{trait}/{breakpoint}: trait statistics unavailable')
            continue
        if not 0 <= float(rate) <= 1:
            raise DataError('Trait top-4 rates must be between 0 and 1')
        count = entity.values.get(f'sample_count_{breakpoint}')
        samples = stat.sample_count if stat else (count.value if count else None)
        lobby = lobby_rate(data)
        posterior = float(rate)
        if samples is not None:
            prior = float(tunable(data,'trait_prior_strength'))
            if samples < 0 or prior < 0:
                raise DataError('Trait sample counts and prior strength must be nonnegative')
            certainty = samples / (samples + prior) if samples + prior else 0.0
            posterior = certainty * posterior + (1-certainty) * lobby
            confidence = min(confidence,certainty)
            if data.tunables['trait_prior_strength'].source in ('default','carried'):
                confidence = min(confidence,float(tunable(data,'confidence_medium_min')))
                warnings.append(f'trait_prior_strength: {data.tunables["trait_prior_strength"].source}')
        if not 0 < posterior < 1:
            raise DataError(f'Trait endpoint rate requires sample count and positive trait prior: {trait}/{breakpoint}')
        total += logit(posterior) - logit(lobby)
        if stat and (stat.stale or stat.changed):
            confidence = min(confidence, float(tunable(data, 'confidence_medium_min')))
            warnings.append(f'{trait}/{breakpoint}: stale or changed statistics')
    return total, confidence, tuple(warnings)


def generic_items(finished, components, high_cost_finished, data):
    values = tunable(data, 'item_values')
    return finished * float(values['finished']) + components * float(values['component']) + high_cost_finished * float(values['high_cost_bonus'])


def stage_items(stage, data):
    values = keyed(static(data, 'stage_items'), stage)
    if values is None:
        raise DataError(f'Missing stage-average items: {stage}')
    return generic_items(values['finished'], values['component'], values['high_cost_finished'], data)


def item_category(item_id, data):
    entity = data.entities.get(item_id)
    if entity is None or entity.kind != 'item':
        raise DataError(f'Item metadata unavailable: {item_id}')
    category = entity.values.get('category')
    component = entity.values.get('component')
    if component is not None and not isinstance(component.value, bool):
        raise DataError(f'Invalid item component certificate: {item_id}')
    if category is not None:
        if category.value not in ('component', 'finished', 'tool'):
            raise DataError(f'Item category unavailable: {item_id}')
        if component is not None and component.value != (category.value == 'component'):
            raise DataError(f'Conflicting item category certificates: {item_id}')
        return category.value
    if component is not None:
        return 'component' if component.value else 'finished'
    raise DataError(f'Item category unavailable: {item_id}')


def estimate_strength(board: Board, level: int, data: DataSnapshot, *, capacity=None) -> PowerEstimate:
    from .capacity import CapacityModel
    CapacityModel(data).check(board,level,capacity)
    unit_total = 0.0
    confidence = 1.0
    warnings = []
    certificates=[('team_capacity',data.static['team_capacity'])]+[(f'{u.unit_id}.team_slot_cost',data.entities[u.unit_id].values['team_slot_cost']) for u in board.units]
    for label,certificate in certificates:
        if certificate.source in ('default','carried'):
            confidence=min(confidence,float(tunable(data,'confidence_medium_min')))
            warnings.append(f'{label}: {certificate.source}; capacity rule requires qualification')
    counts = {}
    finished = components = bonus = 0
    for unit in board.units:
        entity = data.entities[unit.unit_id]
        power, certainty, flags = unit_power(unit.unit_id, unit.stars, data)
        unit_total += power
        confidence = min(confidence, certainty)
        warnings.extend(flags)
        for item_id in unit.items:
            category = item_category(item_id, data)
            if category == 'component':
                components += 1
            elif category == 'finished':
                finished += 1
                bonus += entity.cost >= 3
            else:
                raise DataError(f'Tool cannot be equipped for board power: {item_id}')
    # Duplicate units contribute power separately but their traits only once.
    from .trait_forms import unit_trait_variants
    for unit_id in sorted({u.unit_id for u in board.units}):
        variants = unit_trait_variants(unit_id, data)
        if len(variants) != 1 and board.trait_counts is None:
            raise DataError(f'Own-board trait counts required for variable trait unit: {unit_id}')
        for trait, count in variants[0].items():
            counts[trait] = counts.get(trait, 0) + count
    traits, trait_confidence, trait_flags = trait_term(board.trait_counts if board.trait_counts is not None else counts, data)
    confidence = min(confidence, trait_confidence)
    warnings.extend(trait_flags)
    units = unit_total * float(tunable(data, 'unit_weight'))
    traits *= float(tunable(data, 'trait_weight'))
    items = generic_items(finished, components, bonus, data) * float(tunable(data, 'item_weight'))
    for name in ('unit_weight', 'trait_weight', 'item_weight'):
        if data.tunables[name].source in ('default', 'carried'):
            confidence = min(confidence, float(tunable(data, 'confidence_medium_min')))
            warnings.append(f'{name}: {data.tunables[name].source}')
    return PowerEstimate(units + traits + items, confidence, units, traits, items, tuple(warnings))


def strength(board: Board, level: int, data: DataSnapshot, *, capacity=None) -> float:
    return estimate_strength(board, level, data,capacity=capacity).power


def win_probability(own: float, opponent: float, stage: int, data: DataSnapshot) -> float:
    scale = keyed(tunable(data, 'win_scale_by_stage'), stage)
    if scale is None:
        scale = tunable(data, 'fight_scale')
    return sigmoid(float(scale) * (own - opponent))


def placement(own: float, opponents: tuple[float, ...], own_hp: float, opponent_hp: tuple[float, ...], stage_damage: float, data: DataSnapshot) -> float:
    if len(opponents) != len(opponent_hp) or stage_damage <= 0:
        raise ValueError('Placement requires aligned HP/powers and positive stage damage')
    a, b = float(tunable(data, 'fight_scale')), float(tunable(data, 'terminal_hp_weight'))
    return 1 + sum(sigmoid(a * (power - own) + b * (hp - own_hp) / stage_damage) for power,hp in zip(opponents, opponent_hp) if hp > 0)


def surviving_units(power_gap: float, stage: int, winner_unit_count: int, data: DataSnapshot) -> float:
    scale = keyed(tunable(data, 'survivor_scale_by_stage'), stage)
    if scale is None:
        raise DataError(f'Missing survivor scale: {stage}')
    return winner_unit_count * sigmoid(float(scale) * power_gap)
