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


def owner_match(units):
    from tests.test_outcomes import match_fixture
    match = match_fixture()
    match['info']['participants'][3]['units'] = [{'character_id': unit, 'tier': 1, 'items': []} for unit in units]
    return match


def test_board_reader_identity_scores_disagreements_against_the_owners_final_match_board(tmp_path):
    from tests.test_harness_metrics import outcome_game

    disagreement = lambda reader, tracking, confidence: {'position': 0, 'zone': 'board',
        'reader_unit_id': reader, 'tracking_unit_id': tracking, 'reader_confidence': confidence,
        'chosen_unit_id': tracking}
    sessions, store, _ = outcome_game(tmp_path, events=(
        ('reader_disagreement', {'disagreements': [disagreement('unit', 'ghost', .42),
            disagreement('ghost', 'unit', .45), disagreement('ghost', 'phantom', .9)]}, NOW+timedelta(seconds=1)),))
    harness = EvaluationHarness(sessions, store, repository=ROOT)
    before = harness.evaluate().metrics['hand_set_checks']['board_reader_identity']
    assert before['value'] is None
    assert before['excluded'] == {'qualified_terminal_identity_unavailable': 3}
    sessions.record_outcome('901', owner_match(['unit']), owner_puuid='owner')
    check = harness.evaluate().metrics['hand_set_checks']['board_reader_identity']
    # Two resolved disagreements in one bucket: the reader was right once.
    assert check['by_reader_confidence']['[0.4,0.5)']['reader_right_share']['value'] == .5
    assert check['by_reader_confidence']['[0.4,0.5)']['reader_right_share']['eligible_rows'] == 2
    assert check['excluded'] == {'final_board_does_not_resolve': 1}
    assert check['truth_source'] == 'riot_match_owner_final_board'


def test_opponent_classifier_compares_stage_labels_with_the_joined_final_match_board(tmp_path):
    from tests.test_harness_metrics import eliminated_rival_game, rival_match

    sessions, store, _ = eliminated_rival_game(tmp_path)
    harness = EvaluationHarness(sessions, store, repository=ROOT)
    sessions.record_outcome('901', rival_match(['unit', 'TFT18_Ghost']), owner_puuid='owner')
    check = harness.evaluate().metrics['hand_set_checks']['classifier']
    assert check['by_player']['opponent']['value'] == 1
    assert check['by_player']['opponent']['eligible_rows'] == 1
    assert check['by_stage']['3']['value'] == 1
    assert 'riot_match_opponent_final_board' in check['truth_sources']
