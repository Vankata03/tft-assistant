"""Ex-post schedules identify actions without importing later state into valuation."""
from datetime import datetime

from tft_data import DataError
from tft_engine import GameSnapshot, Line, simulate_lines
from tft_engine.lines import ObservedLine, horizon_rounds
from tft_engine.lobby import alive_lobby
from tft_engine.opponents import opponents_from_history
from tft_engine.planning import read

from .contracts import json_value
from .identity import digest


def observed_line(batch, context, data):
    snapshot = batch.snapshot_for(context)
    horizon = horizon_rounds(snapshot,data)
    later = [row for row in batch.contexts if row.log_seq >= context.log_seq
        and row.snapshot['round_id'] in horizon]
    if set(horizon)-{row.snapshot['round_id'] for row in later}:
        raise DataError('observed_policy_horizon_unavailable')
    end = max(row.log_seq for row in later)
    until = max(datetime.fromisoformat(row.timestamp) for row in later)
    start = snapshot.captured_at
    for event in batch.observations:
        if event['kind'] != 'capture_gap':
            continue
        begin = event['payload'].get('start')
        finish = datetime.fromisoformat(event['payload']['end'])
        if (begin is None or datetime.fromisoformat(begin) <= until) and finish > start:
            raise DataError('observed_policy_crosses_capture_gap')
    readings = []
    for row in later:
        state = GameSnapshot.from_dict(json_value(row.snapshot))
        if (read(state,data,'inventory_complete') is not True or read(state,data,'level') is None
            or read(state,data,'gold') is None):
            raise DataError('observed_policy_fields_unavailable')
        readings.append((row,state))
    actions = [event for event in batch.observations if context.log_seq < event['seq'] <= end
        and datetime.fromisoformat(event['timestamp']) >= start
        and event['kind'] in ('level_up','roll')]
    from .roll_stops import certify_roll_stops
    roll_counts, certificates = certify_roll_stops(batch,context,data,actions)
    levels, rolls, evidence = {}, {}, []
    for event in actions:
        if event['kind'] == 'roll':
            evidence.append(event['seq'])
            continue
        payload = event['payload']
        before,after = payload.get('before',{}).get('level'),payload.get('after',{}).get('level')
        if type(before) is not int or type(after) is not int or after <= before:
            raise DataError('observed_level_action_unavailable')
        matching = [(row,state) for row,state in readings if row.log_seq > event['seq']
            and state.captured_at == datetime.fromisoformat(event['timestamp'])
            and read(state,data,'level') == after]
        if not matching or payload.get('after_read_at') != event['timestamp']:
            raise DataError('observed_level_action_unavailable')
        round_id = matching[0][1].round_id
        levels[round_id] = max(levels.get(round_id,0),after)
        evidence.append(event['seq'])
    previous = read(snapshot,data,'level')
    for _,state in readings:
        current = read(state,data,'level')
        if current > previous and levels.get(state.round_id,0) < current:
            raise DataError('unconfirmed_observed_level_change')
        if current < previous:
            raise DataError('contradictory_observed_level_change')
        previous = current
    # The round abstraction cannot preserve leveling after rolling in one round.
    for event in actions:
        if event['kind'] != 'level_up':
            continue
        round_id = next((row.snapshot['round_id'] for row in later if row.timestamp == event['timestamp']), None)
        if any(roll['kind'] == 'roll' and roll['seq'] < event['seq']
            and roll['payload'].get('round_id') == round_id for roll in actions):
            raise DataError('observed_intraround_level_roll_order_unsupported')
    schedule = {'levels':levels,'rolls':rolls}
    if roll_counts:
        schedule['observed_rolls'] = roll_counts
    line = (ObservedLine('observed:'+digest(schedule)[:20],levels=levels,observed_rolls=roll_counts)
        if roll_counts else Line('observed:'+digest(schedule)[:20],levels=levels))
    return line, {'stop_certificates':certificates,'action_log_seqs':evidence,'observed_through_seq':end,
        'valuation_policy':'ex_post_action_schedule/original_snapshot_data_history_seed',
        'initial_snapshot_id':snapshot.snapshot_id,'initial_prefix_through_seq':context.prefix_through_seq}


def value_observed_line(batch, context, data):
    line, annotation = observed_line(batch,context,data)
    plan = context.evaluation['plan']
    target = plan['target']
    original = next((row for row in context.evaluation['line_results'].get(target,())
        if row['line']['id'] == plan['line']['id']),None)
    if original is None:
        raise DataError('original_selected_line_unavailable')
    snapshot = GameSnapshot.from_dict(json_value(context.snapshot))
    history = batch.history_for(context)
    opponents = opponents_from_history(history,snapshot.round_id,data,opponent_ids=tuple(alive_lobby(snapshot,data)))
    scored = simulate_lines(snapshot,history,data,target,(line,),seed=context.seed,
        backup_id=plan['backup'],rollouts=len(original['rollout_placements']),opponents=opponents)[0]
    return {'option_id':line.id,'action':'line','payload':line.to_dict()|annotation|{'after':scored.to_dict()},
        'expected_placement':scored.expected_placement,'standard_error':scored.standard_error,
        'reason':'observed_action_schedule'}, original
