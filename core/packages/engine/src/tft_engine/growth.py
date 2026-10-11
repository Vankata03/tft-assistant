"""Statistics-derived par growth; callers may retain the immutable result at refresh."""
from typing import Mapping
from tft_data.models import DataError, freeze
from .power import static, tunable, keyed, unit_power, stage_items
from .opponents import round_index, unit_play_rate


def calendar_value(table: Mapping, round_id, data):
    eligible = [r for r in table if round_index(r,data) <= round_index(round_id,data)]
    if not eligible:
        raise DataError(f'No calendar entry before {round_id}')
    return table[max(eligible,key=lambda r:round_index(r,data))]


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


def average_unit_power(level, round_id, data):
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
        weighted = [(unit_play_rate(e.id,data),expected_unit_power(e.id,round_id,data)[0]) for e in roster]
        total += chance * sum(rate * power for rate,power in weighted) / sum(rate for rate,_ in weighted)
    return total


def growth_curve_lookup(round_id, data, *, curve=None):
    if curve is None and 'opponent_growth_curve' in data.tunables:
        curve=tunable(data,'opponent_growth_curve')
    if curve is not None and round_id in curve:
        return float(curve[round_id])
    level = standard_level(round_id,data)
    stage = int(round_id.split('-')[0])
    return level * average_unit_power(level,round_id,data) * float(tunable(data,'unit_weight')) + stage_items(stage,data) * float(tunable(data,'item_weight'))


def growth_curve(data, *, observations=()):
    """Build round powers and a weighted correction from (round, power, confidence) observations."""
    rounds = static(data,'round_order') if 'round_order' in data.static else tuple(static(data,'level_calendar'))
    # A refresh recomputes from the new snapshot, never from the carried curve.
    base = {r:growth_curve_lookup(r,data,curve={}) for r in rounds}
    by_stage = {}
    for round_id,power,confidence in observations:
        if confidence <= 0:
            continue
        stage = round_id.split('-')[0]
        residual = power - growth_curve_lookup(round_id,data,curve={})
        weighted, total = by_stage.get(stage,(0.0,0.0))
        by_stage[stage] = weighted + confidence * residual, total + confidence
    return freeze({r:p + (by_stage[r.split('-')[0]][0] / by_stage[r.split('-')[0]][1] if r.split('-')[0] in by_stage else 0) for r,p in base.items()})
