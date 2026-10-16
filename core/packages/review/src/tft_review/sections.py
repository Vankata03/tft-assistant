"""Descriptive sections keep predictions distinct from subsequent observations."""
from datetime import datetime
from tft_data.models import DataError

from .predictions import fight_forecast


def line_header(result):
    """Copy the scored chart values without copying a rollout distribution."""
    if result is None:
        return None
    return {'line_id': result['line']['id'], 'schedule': result['line'],
        **{name: result.get(name) for name in ('expected_placement', 'standard_error',
            'death_probability', 'hit_probability', 'confidence', 'death_placement_cost')},
        'projections': result.get('projections', ())}


def surface_sections(detail, timeline):
    """Small descriptive records for normal review; raw evidence stays separate."""
    lines = []
    for index, row in enumerate(detail['lines']):
        actual = row['actual_policy']
        actual_result = actual['payload'].get('after') if actual else None
        lines.append({name: row[name] for name in ('log_seq', 'round_id', 'observed', 'pin', 'unavailable')} | {
            'recommended': line_header(row['recommended']), 'actual': line_header(actual_result),
            'pinned': line_header(row['pinned']), 'pin_cost': row['pin_cost'],
            'evidence_path': ['lines', index]})
    return {'lines': tuple(lines),
        'plan_timeline': tuple({name: row.get(name) for name in ('log_seq', 'round_id',
            'status', 'target', 'backup', 'candidates', 'called_status', 'observed_lock',
            'pivot_from', 'pivot_to', 'pivot_round', 'rejected_target', 'player_label',
            'divergence_round', 'planning_round', 'target_similarity')}
            | {'evidence_path': ['plan_timeline', index]}
            for index, row in enumerate(detail['plan_timeline'])),
        'fights': tuple({name: row.get(name) for name in ('round_id', 'opponent_id',
            'start_log_seq', 'start_at', 'result', 'actual_hp_loss', 'win_probability',
            'predicted_hp_loss', 'confidence', 'opponent_warning', 'winner_unit_count',
            'winner_unit_count_source', 'unavailable')}
            | {'evidence_path': ['fights', index]}
            for index, row in enumerate(detail['fights'])),
        'timeline': tuple({name: row[name] for name in ('moment_id', 'engine_decision_id',
            'log_seq', 'round_id', 'category', 'cost', 'paired_uncertainty', 'close_call',
            'differed', 'shown', 'reason', 'unavailable', 'evidence_path')}
            for row in timeline),
        'positioning': tuple({'log_seq': row['log_seq'],
            'engine_decision_id': row['engine_decision_id'], 'cost': None, 'reason': row['reason'],
            'action': row['advice']['action'], 'confidence': row['advice']['confidence'],
            'layout': row['advice'].get('payload', {}).get('layout'),
            **{key: row.get(key) for key in ('shown', 'followed', 'result', 'win_probability', 'fight_path')},
            'unavailable': {} if row.get('followed') is not None else {'followed': 'prefight_board_unavailable'},
            'evidence_path': ['positioning', index]}
            for index, row in enumerate(detail['positioning']))}


def sections(batch, data=None, *, policies=None, timeline=()):
    lines, plans, fights, positioning = [], [], [], []
    for context in batch.contexts:
        fields = context.snapshot['fields']
        observed = {name: fields[name]['value'] if name in fields else None for name in ('gold', 'level', 'hp')}
        evaluation = context.evaluation
        if evaluation is None:
            continue
        plan = evaluation['plan']
        target = plan.get('target')
        line_rows = evaluation.get('line_results', {}).get(target, ())
        recommended = min(line_rows, key=lambda row: (row['expected_placement'], row['line']['id']), default=None)
        projected = batch.snapshot_for(context).fields.get('pinned_line')
        pin = projected.value if projected else None
        pinned = next((row for row in line_rows if pin and row['line']['id'] == pin.get('id')), None)
        pin_cost = recommended['expected_placement']-pinned['expected_placement'] if recommended and pinned else None
        actual = (policies or {}).get(context.log_seq)
        lines.append({'log_seq': context.log_seq, 'round_id': context.snapshot['round_id'],
            'observed': observed, 'recommended': recommended, 'pin': pin, 'pinned': pinned, 'pin_cost': pin_cost,
            'actual_policy': actual, 'unavailable': {} if actual else {'actual_policy': 'player_policy_not_identified'}})
        pivot = next((row for row in timeline if row['log_seq'] == context.log_seq and row['category'] == 'pivot'), None)
        called = pivot and pivot['shown'].get('shown_option_id') is not None
        taken = pivot and pivot['player_choice'] is not None
        called_status = ('called_and_taken' if taken and pivot['player_choice']['option_id'] == pivot['shown'].get('shown_option_id')
            else 'called_and_ignored') if called and taken else ('called_action_unknown' if called
            else 'taken_without_call' if taken else 'display_attribution_unavailable')
        plans.append({'log_seq': context.log_seq, 'round_id': context.snapshot['round_id'],
            **dict(plan), 'called_status': called_status,
            'observed_lock': fields.get('comp_lock', {}).get('value')})
    for record in batch.records:
        if record.decision == 'positioning':
            positioning.append({'log_seq': record.log_seq, 'engine_decision_id': record.decision_id,
                'advice': record.advice, 'cost': None, 'reason': 'rule_based_positioning_not_costed'})
    for event in batch.observations:
        if event['kind'] != 'fight_start':
            continue
        payload = event['payload']
        candidates = [context for context in batch.contexts if context.log_seq < event['seq']
            and context.snapshot['round_id'] == payload['round_id']
            and datetime.fromisoformat(context.timestamp) <= datetime.fromisoformat(event['timestamp'])]
        context = candidates[-1] if candidates else None
        results = [row for row in batch.observations if row['seq'] > event['seq']
            and row['kind'] in {'fight_result', 'fight_incomplete'}
            and row['payload'].get('round_id') == payload['round_id']
            and row['payload'].get('opponent_id') == payload['opponent_id']]
        outcome = results[0] if len(results) == 1 and results[0]['kind'] == 'fight_result' else None
        row = {'round_id': payload['round_id'], 'opponent_id': payload['opponent_id'],
            'start_log_seq': event['seq'], 'start_at': event['timestamp'],
            'result': outcome['payload'].get('result') if outcome else None,
            'actual_hp_loss': outcome['payload'].get('hp_lost') if outcome else None,
            'win_probability': None, 'predicted_hp_loss': None,
            'unavailable': {'forecast': 'historical_data_or_prefight_context_unavailable'}}
        if data is not None and context is not None:
            try:
                row.update(fight_forecast(batch, context, data, opponent_id=payload['opponent_id'],
                    at=datetime.fromisoformat(event['timestamp'])))
                row['unavailable'] = {} if outcome else {'result': 'unknown_fight'}
            except (DataError, KeyError, ValueError, TypeError) as error:
                row['unavailable'] = {'forecast': str(error)}
        fights.append(row)
    for note in positioning:
        point = next(row for row in timeline if row['engine_decision_id'] == note['engine_decision_id'] and row['log_seq'] == note['log_seq'])
        note['shown'] = point['shown']
        note['followed'] = None if point['player_choice'] is None else not point['differed']
        fight = next(((index, row) for index, row in enumerate(fights) if row['start_log_seq'] > note['log_seq']
            and row['round_id'] == point['round_id']), None)
        note.update({'result': fight[1]['result'] if fight else None,
            'win_probability': fight[1]['win_probability'] if fight else None,
            'fight_path': ['surface', 'fights', fight[0]] if fight else None})
    per_fight = []
    for index, fight in enumerate(fights):
        candidates = [note for note in positioning if note.get('fight_path') == ['surface', 'fights', index]]
        if candidates:
            per_fight.append(max(candidates, key=lambda row: row['log_seq']))
        else:
            per_fight.append({'log_seq': fight['start_log_seq'], 'engine_decision_id': None,
                'advice': {'action': 'No layout advised', 'confidence': None, 'payload': {}},
                'cost': None, 'reason': 'no_layout_advised', 'followed': None, 'shown': None,
                'result': fight['result'], 'win_probability': fight['win_probability'],
                'fight_path': ['surface', 'fights', index]})
    positioning = per_fight
    debug = {'raw_snapshot_count': len(batch.contexts),
        'evaluated_snapshot_count': sum(context.evaluation is not None for context in batch.contexts),
        'gap_events': tuple(event for event in batch.observations if event['kind'] == 'capture_gap'),
        'disagreements': tuple(event for event in batch.observations if event['kind'] in {
            'reader_tracker_disagreement', 'tracking_ambiguity', 'board_read_disagreement'}),
        'silences': tuple({'log_seq': context.log_seq, 'reasons': context.unavailable}
            for context in batch.contexts if context.unavailable and context.unavailable != ('semantic_duplicate',)),
        'media': tuple(event for event in batch.observations if event['kind'] in {'keyframe', 'video'})}
    return {'lines': tuple(lines), 'plan_timeline': tuple(plans), 'fights': tuple(fights),
        'positioning': tuple(positioning), 'debug': debug}
