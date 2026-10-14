"""Shared frozen pre-fight forecasts for review and the evaluation harness."""
from tft_data.models import DataError
from tft_engine import GameSnapshot, estimate_strength, surviving_units, win_probability
from tft_engine.effects import captured
from tft_engine.opponents import opponents_from_history
from tft_engine.power import keyed
from tft_engine.growth import par_unit_count
from tft_engine.capacity_fields import evidence_from_snapshot
from tft_engine.planning import read, required
from dataclasses import replace

from .contracts import json_value


def fight_forecast(batch, context, data, *, opponent_id, at):
    if 'capture_gap' in context.unavailable:
        raise DataError('capture_gap')
    snapshot = GameSnapshot.from_dict(json_value(context.snapshot))
    if at < snapshot.captured_at:
        raise DataError('prefight_context_from_future')
    checked = replace(snapshot, captured_at=at)
    if data.static['round_types'].value.get(snapshot.round_id) != 'combat':
        raise DataError('non_player_combat')
    if (read(checked, data, 'inventory_complete') is not True
        or required(checked, data, ('board','level','inventory_complete'))):
        raise DataError('stale_or_incomplete_prefight_ownership')
    capacity = evidence_from_snapshot(checked, data)
    own = estimate_strength(read(checked, data, 'board'), read(checked, data, 'level'), data, capacity=capacity)
    effects = captured(checked, data)
    own_power = own.power+(effects.one_round_power_bonus if effects else 0)
    opponent = next(row for row in opponents_from_history(batch.history_for(context), snapshot.round_id,
        data, opponent_ids=(opponent_id,)) if row.opponent_id == opponent_id)
    stage = int(snapshot.round_id.split('-')[0])
    rules = data.static['player_damage'].value
    base = keyed(rules['stage_base'], stage)
    count = opponent.expected_unit_count
    if count is None:
        count = par_unit_count(snapshot.round_id, data)
    damage = base+rules['per_survivor']*surviving_units(opponent.power-own_power, stage, count, data)
    return {'win_probability': win_probability(own_power, opponent.power, stage, data),
        'predicted_hp_loss': damage, 'naive_damage': base, 'own_power': own_power,
        'opponent_power': opponent.power, 'winner_unit_count': count,
        'winner_unit_count_source': 'inference/par physical-count approximation; not observed',
        'confidence': own.confidence*opponent.confidence, 'opponent_warning': opponent.warnings,
        'seed': context.seed, 'data_snapshot_id': data.snapshot_id, 'log_seq': context.log_seq}
