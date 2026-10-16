"""Hand-set checks are reports from actual replay and observable outcome evidence."""
import json
from datetime import timedelta

import pytest

from tft_engine import Advice, DomainHook
from tft_harness import EvaluationHarness
from tests.test_replay_contracts import NOW, ROOT, logged_game, log_snapshot


def cap_sensitive_advice(context):
    wide = context.data.tunables['open_candidate_count'].value > 1
    return (Advice('reference', 'Wide' if wide else 'Narrow', 'information', .9, 'fixture'),)


def test_widened_candidate_check_replays_actual_engine_with_raised_caps_and_reports_no_truth(tmp_path):
    sessions, store, data, _ = logged_game(tmp_path, mode='silent')
    before = store.get(data.snapshot_id)
    harness = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('reference', (), advice=cap_sensitive_advice),))
    checks = harness.hand_set_checks()
    assert checks['status'] == 'report_only'
    wide = checks['widened_candidates']
    assert wide['changed_decisions'] == 1
    assert wide['eligible_decisions'] == 2
    assert wide['changed_share'] == .5
    assert wide['largest_changes'] == ()
    assert wide['parameters']['gold_floors'] == (0, 10, 20, 30, 40, 50)
    assert wide['parameters']['all_in_rounds_left'] > 100
    assert wide['parameters']['stabilize_rounds_left'] > 100
    assert checks['classifier']['value'] is None
    assert checks['classifier']['excluded']['terminal_boards_unavailable'] == 1
    assert checks['board_reader_identity']['value'] is None
    assert checks['confidence_bands']['ordering']['status'] == 'unavailable'
    assert store.get(data.snapshot_id) == before
    with pytest.raises(TypeError):
        checks['status'] = 'gate'
    json.dumps(dict(checks), default=lambda value: dict(value), allow_nan=False)


def test_owner_classifier_uses_qualified_end_phase_board_from_own_game_log(tmp_path):
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='baseline')
    at = NOW+timedelta(seconds=1)
    raw = log_snapshot(data, at=at, snapshot_id='terminal', phase='end', planning_phase=False, hp=0)
    sessions.append_event('snapshot', raw, timestamp=at.isoformat())
    sessions.end_game(placement=4, timestamp=at.isoformat())
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    check = report.metrics['hand_set_checks']['classifier']
    assert check['value'] == 1
    assert check['eligible_rows'] == 1
    assert check['by_stage']['3']['value'] == 1
    assert check['truth_sources'] == ('own_terminal_capture',)
    assert 'classifier' not in report.gates


def test_confidence_check_fails_flat_accuracy_across_three_banded_games(tmp_path):
    """Bands come from each game's pinned thresholds; equal loss is not an improvement."""
    import tomllib
    import tomli_w
    from tft_core.storage import SessionStore
    from tests.test_replay_contracts import historical_data, GuideFeed

    store, _ = historical_data(tmp_path)
    path = tmp_path/'patch'/'static.toml'
    config = tomllib.loads(path.read_text())
    config['fields']['round_types']['value']['3-2'] = 'combat'
    path.write_text(tomli_w.dumps(config))
    tunables_path = tmp_path/'patch'/'tunables.toml'
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.set_mode('silent')
    # A trait-less sighting has zero inferred confidence, so thresholds at zero
    # place the same forecast in the medium or high band.
    for index, (medium, high) in enumerate(((.5, .8), (0, .8), (0, 0))):
        tunables = tomllib.loads(tunables_path.read_text())
        tunables['fields']['confidence_medium_min']['value'] = medium
        tunables['fields']['confidence_high_min']['value'] = high
        tunables_path.write_text(tomli_w.dumps(tunables))
        at = NOW+timedelta(days=index)
        refreshed = store.refresh(tunables_path.parent, now=at+timedelta(seconds=1), sources=(GuideFeed(),))
        assert refreshed.error is None
        data = refreshed.snapshot
        game_id = str(901+index)
        sessions.start_game(game_id, set_id='18', patch=data.patch, data_snapshot_id=data.snapshot_id,
            timestamp=at.isoformat())
        sessions.append_event('sighting', {'opponent_id': 'rival', 'round_id': '3-2',
            'level': 1, 'traits': {}, 'hidden_traits': 0}, timestamp=at.isoformat())
        raw = log_snapshot(data, at=at)|{'game_id': game_id}
        sessions.append_event('snapshot', raw, timestamp=at.isoformat())
        sessions.append_event('fight_start', {'round_id': '3-2', 'opponent_id': 'rival'},
            timestamp=(at+timedelta(seconds=1)).isoformat())
        sessions.append_event('fight_result', {'round_id': '3-2', 'opponent_id': 'rival', 'result': 'loss', 'hp_lost': 5},
            timestamp=(at+timedelta(seconds=2)).isoformat())
        sessions.end_game(placement=4, timestamp=(at+timedelta(seconds=3)).isoformat())
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    checks = report.metrics['hand_set_checks']['confidence_bands']['by_metric']['fight_brier']
    assert {name: row['value'] for name, row in checks['bands'].items()} == {'low': .25, 'medium': .25, 'high': .25}
    assert checks['ordering']['status'] == 'fail'
    assert 'hand_set_checks' not in report.gates
