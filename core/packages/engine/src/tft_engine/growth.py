"""Statistics-derived par growth; callers may retain the immutable result at refresh."""
from typing import Mapping
from math import isfinite
from tft_data.models import DataError, freeze
from .power import static, tunable, keyed, unit_power, stage_items
from .opponents import round_index, unit_play_rate
from .preparation import patch_calculation


def calendar_value(table: Mapping, round_id, data):
    eligible = [r for r in table if round_index(r,data) <= round_index(round_id,data)]
    if not eligible:
        raise DataError(f'No calendar entry before {round_id}')
    return table[max(eligible,key=lambda r:round_index(r,data))]


@patch_calculation
def standard_level(round_id, data):
    return int(calendar_value(static(data,'level_calendar'),round_id,data))


def star_mix(round_id, cost, data):
    by_cost = calendar_value(tunable(data,'opponent_star_mix'),round_id,data)
    mix = keyed(by_cost,cost)
    if mix is None or len(mix) != 3 or any(p < 0 for p in mix) or abs(sum(mix)-1) > 1e-9:
        raise DataError(f'Invalid or missing star mix for {round_id}, cost {cost}')
    return mix


def expected_unit_power(unit_id, round_id, data):
    mix = star_mix(round_id,data.entities[unit_id].cost,data)
    total, confidence = 0.0, 1.0
    warnings = []
    for stars, share in enumerate(mix,1):
        if not share:
            continue
        power, certainty, flags = unit_power(unit_id,stars,data)
        total += share * power
        confidence = min(confidence,certainty)
        warnings.extend(flags)
    return total, confidence, tuple(warnings)


def average_unit_power(level, round_id, data, *, count_only=False):
    from .capacity import CapacityModel
    capacity=CapacityModel(data)
    odds = keyed(static(data,'shop_odds'),level)
    if odds is None or len(odds) != 5 or any(p < 0 for p in odds) or abs(sum(odds)-1) > 1e-9:
        raise DataError(f'Invalid or missing shop odds for level {level}')
    total = 0.0
    for cost, chance in enumerate(odds,1):
        if not chance:
            continue
        roster = [e for e in data.entities.values() if e.kind == 'unit' and e.cost == cost]
        if not roster:
            raise DataError(f'No roster for shop cost {cost}')
        weighted=[]
        for entity in roster:
            cost=capacity.cost(entity.id)
            if cost<=0:
                raise DataError('Zero-slot units require a sourced par frequency model')
            weighted.append((unit_play_rate(entity.id,data),(1 if count_only else expected_unit_power(entity.id,round_id,data)[0])/cost))
        total += chance * sum(rate * power for rate,power in weighted) / sum(rate for rate,_ in weighted)
    return total


@patch_calculation
def par_unit_count(round_id,data):
    """Physical-unit approximation from the sourced base budget and slot mix."""
    from .capacity import CapacityModel
    level=standard_level(round_id,data)
    return min(28,CapacityModel(data).base(level)*average_unit_power(level,round_id,data,count_only=True))


def growth_curve_lookup(round_id, data, *, curve=None, apply_correction=True):
    if curve is None and apply_correction:
        return _default_growth_lookup(round_id, data)
    return _growth_curve_lookup(round_id, data, curve=curve, apply_correction=apply_correction)


@patch_calculation
def _default_growth_lookup(round_id, data):
    return _growth_curve_lookup(round_id, data)


def _growth_curve_lookup(round_id, data, *, curve=None, apply_correction=True):
    if curve is None and 'opponent_growth_curve' in data.tunables:
        curve=tunable(data,'opponent_growth_curve')
    correction = 1.
    if apply_correction and 'opponent_growth_correction_by_stage' in data.tunables:
        table = tunable(data, 'opponent_growth_correction_by_stage')
        if not isinstance(table, Mapping):
            raise DataError('Opponent growth correction requires a stage map')
        correction = table.get(round_id.split('-')[0], 1.)
        if isinstance(correction, bool) or not isinstance(correction, (int, float)) or not isfinite(correction) or correction <= 0:
            raise DataError('Opponent growth correction must be finite and positive')
    if curve is not None and round_id in curve:
        return float(curve[round_id])*correction
    level = standard_level(round_id,data)
    stage = int(round_id.split('-')[0])
    from .capacity import CapacityModel
    # Par has no captured item/augment/trait activation. It values the explicit
    # level budget in slot-average units, without inventing those modifiers.
    return correction*(CapacityModel(data).base(level) * average_unit_power(level,round_id,data) * float(tunable(data,'unit_weight')) + stage_items(stage,data) * float(tunable(data,'item_weight')))


def growth_curve(data, *, observations=()):
    """Build round powers and a weighted correction from (round, power, confidence) observations."""
    rounds = static(data,'round_order') if 'round_order' in data.static else tuple(static(data,'level_calendar'))
    # Store an uncorrected refresh curve; runtime lookup applies the optional
    # fitted multiplier once, including when this table is cached.
    base = {r:growth_curve_lookup(r,data,curve={},apply_correction=False) for r in rounds}
    by_stage = {}
    for round_id,power,confidence in observations:
        if confidence <= 0:
            continue
        stage = round_id.split('-')[0]
        residual = power - growth_curve_lookup(round_id,data,curve={},apply_correction=False)
        weighted, total = by_stage.get(stage,(0.0,0.0))
        by_stage[stage] = weighted + confidence * residual, total + confidence
    return freeze({r:p + (by_stage[r.split('-')[0]][0] / by_stage[r.split('-')[0]][1] if r.split('-')[0] in by_stage else 0) for r,p in base.items()})
