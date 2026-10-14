"""Causal UI controls projected from real committed session logs."""
from datetime import datetime, timedelta

import pytest

from tests.test_replay_contracts import NOW, ROOT, logged_game, log_snapshot
from tft_engine import GameSnapshot, Line


def pin_payload(data, *, line_id='kept-line'):
    return {'delivery_revision': 'sha256:'+'a'*64, 'game_id': '901',
        'data_snapshot_id': data.snapshot_id,
        'pin': {'comp_id': 'guide', 'line_id': line_id, 'seed': '123'},
        'schedule': Line(line_id, {'3-2': 1}).to_dict()}


def test_causal_projection_keeps_accepted_pin_time_and_original_capture_fields(tmp_path):
    from tft_review import project_session_controls

    sessions, _, data, _ = logged_game(tmp_path, finish=False, mode='live')
    accepted_at = NOW+timedelta(seconds=.1)
    accepted = sessions.append_event('line_pin', pin_payload(data), timestamp=accepted_at.isoformat())
    captured_at = NOW+timedelta(seconds=30)
    raw = log_snapshot(data, at=captured_at, snapshot_id='later')
    raw['fields']['gold']['read_at'] = NOW.isoformat()
    recorded = sessions.append_event('snapshot', raw, timestamp=captured_at.isoformat())
    original = GameSnapshot.from_dict(raw)
    projected = project_session_controls(original, sessions.read_events('901'), through_seq=recorded['seq']-1)
    assert projected.snapshot.fields['pinned_line'].value['id'] == 'kept-line'
    assert projected.snapshot.fields['pinned_line'].read_at == accepted_at
    assert projected.snapshot.fields['pinned_line'].source == 'ui_pin'
    assert projected.snapshot.captured_at == captured_at
    assert projected.snapshot.fields['gold'].read_at == NOW
    assert 'pinned_line' not in original.fields
    assert projected.provenance['line_pin']['log_seq'] == accepted['seq']
    assert projected.provenance['line_pin']['timestamp'] == accepted_at.isoformat()


def control_advice(context):
    from tft_engine import Advice
    pin = context.snapshot.fields.get('pinned_line')
    history = context.history.snapshots
    return (Advice('controls', 'Recorded controls', 'information', 1, 'fixture-hook',
        payload={'pin': pin.value if pin else None,
            'read_at': pin.read_at.isoformat() if pin else None,
            'history': [{'snapshot_id': row.snapshot_id,
                'pin': row.fields['pinned_line'].value if 'pinned_line' in row.fields else None}
                for row in history]}),)


def test_replay_projects_each_frame_own_control_prefix_without_rewriting_raw_contexts(tmp_path):
    from tft_engine import DomainHook, snapshot_seed
    from tft_review import ReplayBatch, ReplayProducer

    sessions, store, data, original = logged_game(tmp_path, finish=False, mode='live')
    accepted_at = NOW+timedelta(seconds=.1)
    accepted = sessions.append_event('line_pin', pin_payload(data), timestamp=accepted_at.isoformat())
    first_at = NOW+timedelta(seconds=.25)
    first = sessions.append_event('snapshot', log_snapshot(data, at=first_at, snapshot_id='pinned'),
        timestamp=first_at.isoformat())
    second_at = NOW+timedelta(seconds=30)
    second = sessions.append_event('snapshot', log_snapshot(data, at=second_at, snapshot_id='persistent'),
        timestamp=second_at.isoformat())
    # This later command is not visible to either previous capture.
    sessions.append_event('line_pin', dict(pin_payload(data), pin=None, schedule=None),
        timestamp=(NOW+timedelta(seconds=31)).isoformat())
    third_at = NOW+timedelta(seconds=32)
    sessions.append_event('snapshot', log_snapshot(data, at=third_at, snapshot_id='unpinned'),
        timestamp=third_at.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=33)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT,
        hooks=(DomainHook('controls', (), advice=control_advice, dependency_fields=('pinned_line',)),)).produce('901')
    first_payload = next(row['payload'] for row in batch.contexts[1].evaluation['advice'] if row['decision'] == 'controls')
    assert first_payload['pin']['id'] == 'kept-line'
    assert first_payload['read_at'] == accepted_at.isoformat()
    assert first_payload['history'] == ({'snapshot_id': 'original', 'pin': None},)
    last_payload = next(row['payload'] for row in batch.contexts[-1].evaluation['advice'] if row['decision'] == 'controls')
    assert last_payload['pin'] is None
    assert [row['pin']['id'] if row['pin'] else None for row in last_payload['history']] == [None, 'kept-line', 'kept-line']
    assert all('pinned_line' not in context.snapshot['fields'] for context in batch.contexts)
    assert batch.contexts[1].evaluation_overlay['provenance']['line_pin']['log_seq'] == accepted['seq']
    assert batch.snapshot_for(batch.contexts[2]).fields['pinned_line'].read_at == accepted_at
    assert batch.contexts[1].seed == snapshot_seed(batch.snapshot_for(batch.contexts[1]), data)
    assert batch.contexts[1].log_seq == first['seq'] and batch.contexts[2].log_seq == second['seq']
    assert batch.contexts[0].log_seq == original['seq']
    assert ReplayBatch.from_dict(batch.to_dict()) == batch


@pytest.mark.parametrize('ending', ['unpin', 'mode', 'detach', 'gap', 'reset'])
def test_controls_clear_on_causal_invalidation_and_never_change_an_earlier_frame(tmp_path, ending):
    from tft_review import project_session_controls

    sessions, _, data, _ = logged_game(tmp_path, finish=False, mode='live')
    accepted = sessions.append_event('line_pin', pin_payload(data), timestamp=(NOW+timedelta(seconds=.1)).isoformat())
    prior = GameSnapshot.from_dict(log_snapshot(data, at=NOW+timedelta(seconds=.2)))
    if ending == 'unpin':
        event = sessions.append_event('line_pin', dict(pin_payload(data), pin=None, schedule=None),
            timestamp=(NOW+timedelta(seconds=1)).isoformat())
    elif ending == 'mode':
        sessions.set_mode('baseline')
        event = sessions.read_events('901')[-1]
    elif ending == 'detach':
        event = sessions.detach_game('901', reason='identity_lost', timestamp=(NOW+timedelta(seconds=1)).isoformat())
    elif ending == 'gap':
        event = sessions.append_event('capture_gap', {'start': NOW.isoformat(),
            'end': (NOW+timedelta(seconds=1)).isoformat(), 'reason': 'core_restart'},
            timestamp=(NOW+timedelta(seconds=1)).isoformat())
    else:
        event = sessions.append_event('session_controls_reset', {'game_id': '901',
            'data_snapshot_id': data.snapshot_id, 'reason': 'authenticated_client_disconnected'},
            timestamp=(NOW+timedelta(seconds=1)).isoformat())
    if event is None:
        event = sessions.read_events('901')[-1]
    events = sessions.read_events('901')
    earlier = project_session_controls(prior, events, through_seq=accepted['seq'])
    assert earlier.snapshot.fields['pinned_line'].value['id'] == 'kept-line'
    at = datetime.fromisoformat(event['timestamp'])+timedelta(seconds=.1)
    later = project_session_controls(GameSnapshot.from_dict(log_snapshot(data, at=at)), events,
        through_seq=event['seq'])
    assert 'pinned_line' not in later.snapshot.fields
    assert later.provenance['reset']['log_seq'] == event['seq']


@pytest.mark.parametrize('changed', ['other_game', 'other_data', 'different_line', 'bool_level',
    'negative_roll', 'bad_seed', 'bad_revision', 'missing_schedule', 'wrong_mode'])
def test_invalid_durable_pin_never_becomes_an_engine_input(tmp_path, changed):
    from tft_review import project_session_controls

    sessions, _, data, _ = logged_game(tmp_path, finish=False,
        mode='baseline' if changed == 'wrong_mode' else 'live')
    payload = pin_payload(data)
    if changed == 'other_game': payload['game_id'] = '902'
    elif changed == 'other_data': payload['data_snapshot_id'] = 'f'*64
    elif changed == 'different_line': payload['schedule']['id'] = 'other'
    elif changed == 'bool_level': payload['schedule']['levels'] = {'3-2': True}
    elif changed == 'negative_roll': payload['schedule']['rolls'] = {'3-2': -1}
    elif changed == 'bad_seed': payload['pin']['seed'] = True
    elif changed == 'bad_revision': payload['delivery_revision'] = 'not-authenticated'
    elif changed == 'missing_schedule': payload.pop('schedule')
    event = sessions.append_event('line_pin', payload, timestamp=(NOW+timedelta(seconds=.1)).isoformat())
    snapshot = GameSnapshot.from_dict(log_snapshot(data, at=NOW+timedelta(seconds=.2)))
    with pytest.raises(ValueError, match='[Pp]in'):
        project_session_controls(snapshot, sessions.read_events('901'), through_seq=event['seq'])


def test_future_dated_pin_and_later_sequence_are_not_available_to_old_capture(tmp_path):
    from tft_review import project_session_controls

    sessions, _, data, first = logged_game(tmp_path, finish=False, mode='live')
    future = sessions.append_event('line_pin', pin_payload(data),
        timestamp=(NOW+timedelta(seconds=10)).isoformat())
    early = GameSnapshot.from_dict(log_snapshot(data, at=NOW+timedelta(seconds=1)))
    assert 'pinned_line' not in project_session_controls(early, sessions.read_events('901'),
        through_seq=future['seq']).snapshot.fields
    late = GameSnapshot.from_dict(log_snapshot(data, at=NOW+timedelta(seconds=11)))
    assert 'pinned_line' not in project_session_controls(late, sessions.read_events('901'),
        through_seq=first['seq']).snapshot.fields


def test_replay_roundtrip_rejects_a_fabricated_control_overlay(tmp_path):
    from tft_engine import DomainHook
    from tft_review import ReplayBatch, ReplayProducer

    sessions, store, _, _ = logged_game(tmp_path, mode='baseline')
    batch = ReplayProducer(sessions, store, repository=ROOT,
        hooks=(DomainHook('controls', (), advice=control_advice),)).produce('901')
    changed = batch.to_dict()
    changed['contexts'][0]['evaluation_overlay']['fields']['pinned_line'] = {
        'value': {'id': 'never-accepted'}, 'read_at': NOW.isoformat(), 'source': 'ui_pin', 'confidence': 1}
    with pytest.raises(ValueError, match='control overlay'):
        ReplayBatch.from_dict(changed)


def test_normal_review_line_section_exposes_recorded_pin_without_claiming_a_player_policy(tmp_path):
    from tft_engine import DomainHook
    from tft_review import ReplayProducer, ReviewPolicy

    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='live')
    sessions.append_event('line_pin', pin_payload(data), timestamp=(NOW+timedelta(seconds=.1)).isoformat())
    at = NOW+timedelta(seconds=.25)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='pinned'), timestamp=at.isoformat())
    sessions.end_game(timestamp=(at+timedelta(seconds=1)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT,
        hooks=(DomainHook('controls', (), advice=control_advice),)).produce('901')
    report = ReviewPolicy(min_cost=.05).build(batch, data=data)
    assert report.surface['lines'][-1]['pin']['id'] == 'kept-line'
    assert report.surface['lines'][-1]['actual'] is None
    assert report.surface['lines'][-1]['unavailable']['actual_policy'] == 'player_policy_not_identified'


def test_actual_engine_replay_uses_a_causally_accepted_scored_line_pin(tmp_path):
    from tft_review import ReplayProducer

    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='live')
    producer = ReplayProducer(sessions, store, repository=ROOT)
    initial = producer.produce('901')
    evaluation = initial.to_dict()['contexts'][0]['evaluation']
    target = evaluation['plan']['target']
    chosen = evaluation['line_results'][target][-1]['line']
    payload = pin_payload(data, line_id=chosen['id'])
    payload['pin']['comp_id'] = target
    payload['schedule'] = dict(chosen)
    sessions.append_event('line_pin', payload, timestamp=(NOW+timedelta(seconds=.1)).isoformat())
    at = NOW+timedelta(seconds=.25)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='engine-pin'), timestamp=at.isoformat())
    sessions.end_game(timestamp=(at+timedelta(seconds=1)).isoformat())
    batch = producer.produce('901')
    advice = next(row for row in batch.contexts[-1].evaluation['advice'] if row['decision'] == 'econ')
    assert advice['payload']['pinned'] is True
    assert batch.contexts[-1].evaluation['plan']['line']['id'] == chosen['id']
    assert 'pinned_line' not in batch.contexts[-1].snapshot['fields']
