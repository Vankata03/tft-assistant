"""Replay resource behavior at the real log and Engine boundary."""
from datetime import timedelta

import pytest

from tests.test_replay_contracts import NOW, ROOT, logged_game, log_snapshot
from tft_engine import DomainHook, evaluate
from tft_review import ReplayBatch, ReplayProducer


_FIT_CALLS = []


def count_fit(comp_id, context):
    _FIT_CALLS.append(context.snapshot.snapshot_id)
    return None


def test_replay_reuses_historical_planning_without_changing_causal_evaluations(tmp_path):
    sessions, store, data, _ = logged_game(tmp_path, finish=False)
    for index in range(1, 8):
        at = NOW+timedelta(seconds=index)
        sessions.append_event('snapshot', log_snapshot(data, at=at,
            snapshot_id=f'decision-{index}', gold=18+index), timestamp=at.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=9)).isoformat())
    hooks = (DomainHook('resource-probe', (), fit=count_fit),)
    _FIT_CALLS.clear()
    batch = ReplayProducer(sessions, store, repository=ROOT, hooks=hooks).produce('901')
    assert _FIT_CALLS == ['original']+[f'decision-{index}' for index in range(1, 8)]
    for context in batch.contexts:
        actual = context.to_dict()['evaluation']
        reference = evaluate(batch.snapshot_for(context), batch.history_for(context),
            data, 'review', seed=context.seed, hooks=hooks)
        from tft_review.contracts import json_value
        expected = json_value(reference)
        actual.pop('simulation_diagnostics')
        expected.pop('simulation_diagnostics')
        assert actual == expected
    import json
    assert len(json.dumps(batch.to_dict(), separators=(',', ':'))) < 8*32_000
    assert ReplayBatch.from_dict(batch.to_dict()) == batch


def test_retained_causal_histories_share_the_immutable_log_instead_of_copying_prefixes(tmp_path):
    import tracemalloc
    from tft_review.contracts import history_prefix
    from tft_review.controls import SessionControlLog

    sessions, _, data, _ = logged_game(tmp_path, finish=False)
    for index in range(1, 300):
        at = NOW+timedelta(seconds=index)
        sessions.append_event('snapshot', log_snapshot(data, at=at,
            snapshot_id=f'decision-{index}'), timestamp=at.isoformat())
    events = sessions.read_events('901')
    controls = SessionControlLog(events)
    frames = [event for event in events if event['kind'] == 'snapshot']
    # Parse/projection storage belongs to the log, not to each retained prefix.
    for frame in frames:
        controls.frame(frame)
    tracemalloc.start()
    histories = [history_prefix(events, through_seq=frame['seq']-1,
        captured_at=frame['payload']['captured_at'], controls=controls) for frame in frames]
    retained, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert [row.snapshots[-1].snapshot_id for row in histories[1:]] == [
        'original']+[f'decision-{index}' for index in range(1, 299)]
    # 300 histories need under 300 KB in addition to the already projected log.
    # Copied pointer prefixes alone consume roughly 360 KB on 64-bit CPython.
    assert retained < 300_000
    import pytest
    with pytest.raises((AttributeError, TypeError)):
        histories[-1].snapshots[0] = histories[-1].snapshots[-1]


def test_compact_replay_history_reconstructs_exact_engine_evidence_and_rejects_forgery(tmp_path):
    import hashlib
    import json
    import pytest
    from dataclasses import replace
    from tft_engine import GameHistory

    sessions, store, data, _ = logged_game(tmp_path, finish=False)
    at = NOW+timedelta(seconds=1)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='second'), timestamp=at.isoformat())
    sessions.end_game(timestamp=(at+timedelta(seconds=1)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    advice = batch.contexts[-1].evaluation['advice'][0]
    reference = advice['validity_state']['history']
    assert reference['source']['kind'] == 'replay_history_v1'
    history = batch.resolve_history(reference, data=data)
    assert [state.snapshot_id for state in history.snapshots] == ['original']
    encoded = json.dumps(history.to_dict(), sort_keys=True, separators=(',', ':'), allow_nan=False)
    assert reference['sha256'] == hashlib.sha256(encoded.encode()).hexdigest()
    assert len(json.dumps(dict(reference) | {'source': dict(reference['source'])})) < 400
    for changed in ({'sha256': '0'*64}, {'source': dict(reference['source']) | {'game_id': '902'}},
        {'source': dict(reference['source']) | {'prefix_through_seq': 999}}):
        with pytest.raises(ValueError, match='[Hh]istory'):
            batch.resolve_history(dict(reference) | changed, data=data)
    with pytest.raises(ValueError, match='[Hh]istory'):
        batch.resolve_history(reference, data=replace(data, snapshot_id='wrong-pin'))
    assert ReplayBatch.from_dict(batch.to_dict()).resolve_history(reference, data=data).to_dict() == history.to_dict()
    # Standalone Engine callers retain their inline evidence contract.
    standalone = evaluate(batch.snapshot_for(batch.contexts[-1]),
        GameHistory(history.snapshots, history.sightings), data, 'review')
    assert standalone.advice[0].validity_state['history']['snapshots'][0]['snapshot_id'] == 'original'


def test_resource_optimizations_preserve_irregular_capture_pin_and_gap_histories(tmp_path):
    from tft_review.contracts import json_value
    from tests.test_session_controls import pin_payload

    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='live')
    sessions.append_event('sighting', {'opponent_id': 'future', 'round_id': '3-2',
        'level': 1, 'traits': {}, 'hidden_traits': 0}, timestamp=(NOW+timedelta(seconds=10)).isoformat())
    # An accepted schedule is intentionally not one of this tiny fixture's
    # candidates; both paths must preserve the same explicit unavailable result.
    sessions.append_event('line_pin', pin_payload(data), timestamp=(NOW+timedelta(seconds=.2)).isoformat())
    sessions.append_event('snapshot', log_snapshot(data, at=NOW+timedelta(seconds=.5),
        snapshot_id='inside-retrospective-gap'), timestamp=(NOW+timedelta(seconds=.5)).isoformat())
    sessions.append_event('snapshot', log_snapshot(data, at=NOW+timedelta(seconds=.25),
        snapshot_id='late-older-capture'), timestamp=(NOW+timedelta(seconds=.75)).isoformat())
    sessions.append_event('sighting', {'opponent_id': 'known', 'round_id': '3-2',
        'level': 1, 'traits': {}, 'hidden_traits': 0}, timestamp=(NOW+timedelta(seconds=.8)).isoformat())
    sessions.append_event('snapshot', log_snapshot(data, at=NOW+timedelta(seconds=1),
        snapshot_id='combat', phase='combat', planning_phase=False), timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.append_event('capture_gap', {'start': (NOW+timedelta(seconds=.4)).isoformat(),
        'end': (NOW+timedelta(seconds=.6)).isoformat(), 'reason': 'late_annotation'},
        timestamp=(NOW+timedelta(seconds=2)).isoformat())
    at = NOW+timedelta(seconds=2.1)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='recovered'), timestamp=at.isoformat())
    sessions.end_game(timestamp=(at+timedelta(seconds=1)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    for context in batch.contexts:
        if context.evaluation is None:
            assert context.snapshot['snapshot_id'] == 'inside-retrospective-gap'
            assert context.unavailable == ('capture_gap',)
            continue
        actual = context.to_dict()['evaluation']
        expected = json_value(evaluate(batch.snapshot_for(context), batch.history_for(context),
            data, 'review', seed=context.seed))
        actual.pop('simulation_diagnostics')
        expected.pop('simulation_diagnostics')
        assert actual == expected
        for advice in context.evaluation['advice']:
            reference = advice['validity_state'].get('history')
            if reference is not None:
                reconstructed = batch.resolve_history(reference, data=data)
                assert all(state.captured_at <= batch.snapshot_for(context).captured_at
                    for state in reconstructed.snapshots)
                assert all(sighting.opponent_id != 'future' for sighting in reconstructed.sightings)
    history = batch.history_for(batch.contexts[-1])
    assert [state.snapshot_id for state in history.snapshots] == ['late-older-capture', 'combat']
    assert batch.snapshot_for(batch.contexts[2]).fields['pinned_line'].read_at == NOW+timedelta(seconds=.2)
    assert 'pinned_line' not in batch.snapshot_for(batch.contexts[-1]).fields


@pytest.mark.parametrize('opaque', [False, True])
def test_stateful_external_hooks_keep_the_original_uncached_historical_fold(tmp_path, opaque):
    calls = []

    def fit(comp_id, context):
        calls.append(context.snapshot.snapshot_id)
        return None

    class OpaqueFit:
        def __call__(self, comp_id, context):
            return fit(comp_id, context)

    sessions, store, data, _ = logged_game(tmp_path, finish=False)
    for index in range(1, 3):
        at = NOW+timedelta(seconds=index)
        sessions.append_event('snapshot', log_snapshot(data, at=at,
            snapshot_id=f'decision-{index}'), timestamp=at.isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    batch = ReplayProducer(sessions, store, repository=ROOT,
        hooks=(DomainHook('external-state', (), fit=OpaqueFit() if opaque else fit),)).produce('901')
    assert batch.identity['hooks_cacheable'] is False
    assert calls == ['original', 'original', 'decision-1', 'original', 'decision-1', 'decision-2']
    assert not any(row['kind'] == 'replay_cache' for row in sessions.read_events('901'))


@pytest.mark.parametrize('future_round', [False, True])
def test_error_path_history_references_preserve_exact_hook_evidence_after_round_trip(tmp_path, future_round):
    from tests.test_session_controls import control_advice
    from tft_engine import GameHistory

    sessions, store, data, _ = logged_game(tmp_path, finish=False)
    later = log_snapshot(data, at=NOW+timedelta(seconds=2), snapshot_id='captured-later')
    if future_round:
        later['round_id'] = '4-1'
    sessions.append_event('snapshot', later, timestamp=later['captured_at'])
    older = log_snapshot(data, at=NOW+timedelta(seconds=1), snapshot_id='captured-earlier')
    sessions.append_event('snapshot', older, timestamp=(NOW+timedelta(seconds=2.1)).isoformat())
    current = log_snapshot(data, at=NOW+timedelta(seconds=3),
        snapshot_id='current-unavailable', comp_lock='unknown-comp')
    sessions.append_event('snapshot', current, timestamp=current['captured_at'])
    sessions.end_game(timestamp=(NOW+timedelta(seconds=4)).isoformat())
    original = sessions.read_events('901')
    hooks = (DomainHook('controls', (), advice=control_advice),)
    batch = ReplayProducer(sessions, store, repository=ROOT, hooks=hooks).produce('901')
    context = batch.contexts[-1]
    paused = next(advice for advice in context.evaluation['advice'] if advice['decision'] == 'econ')
    assert paused['payload']['reason'] == 'Unknown locked comp: unknown-comp'
    advice = next(advice for advice in context.evaluation['advice'] if advice['decision'] == 'controls')
    expected = ['original', 'captured-later', 'captured-earlier']
    assert [row['snapshot_id'] for row in advice['payload']['history']] == expected
    assert sessions.read_events('901')[:len(original)] == original
    restored = ReplayBatch.from_dict(batch.to_dict())
    reference = advice['validity_state']['history']
    history = restored.resolve_history(reference, data=data)
    assert [state.snapshot_id for state in history.snapshots] == expected
    # Standalone handled-error hooks keep the original inline log-order evidence.
    prefix = batch.history_for(context)
    standalone = evaluate(batch.snapshot_for(context), GameHistory(prefix.snapshots, prefix.sightings),
        data, 'review', hooks=hooks, seed=context.seed)
    standalone_advice = next(item for item in standalone.advice if item.decision == 'controls')
    assert history.to_dict() == GameHistory.from_dict(standalone_advice.validity_state['history']).to_dict()
    assert reference['source']['projection'] == 'replay_prefix_v1'
    assert batch.contexts[0].evaluation['advice'][0]['validity_state']['history']['source']['projection'] == 'engine_causal_v1'
    with pytest.raises(ValueError, match='content hash mismatch'):
        restored.resolve_history(dict(reference) | {'source': dict(reference['source']) |
            {'projection': 'engine_causal_v1'}}, data=data)
