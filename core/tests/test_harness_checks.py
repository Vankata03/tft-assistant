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
