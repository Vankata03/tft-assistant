"""Planning-phase reversals through real log replay and declared domain hooks."""
from datetime import timedelta

import pytest

from tft_engine import Advice, DomainHook
from tft_harness import EvaluationHarness
from tests.test_replay_contracts import NOW, ROOT, logged_game, log_snapshot


def oscillating_choices(context):
    # An intentionally defective public extension changes on capture identity.
    changed = context.snapshot.snapshot_id == 'middle'
    if context.data.tunables['unit_weight'].value > 1:
        changed = False
    return (Advice('reference', 'B' if changed else 'A', 'information', .9, 'fixture'),)


def oscillating_logs(tmp_path, *, changed_gold=False, mode='baseline'):
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode=mode)
    for index, name in enumerate(('middle', 'last'), 1):
        at = NOW+timedelta(seconds=index)
        raw = log_snapshot(data, at=at, snapshot_id=name, gold=19 if changed_gold and index == 1 else 18)
        raw['round_id'] = f'3-{index+2}'
        sessions.append_event('snapshot', raw, timestamp=at.isoformat())
    sessions.end_game(placement=4, timestamp=(at+timedelta(seconds=1)).isoformat())
    return EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('reference', ('gold',), advice=oscillating_choices),))


def test_flip_gate_uses_paired_original_points_and_counts_a_b_a_within_three_phases(tmp_path):
    harness = oscillating_logs(tmp_path)
    report = harness.flip_rates(candidate={'unit_weight': 2})
    domain = report['domains']['reference']
    assert domain['flips'] == 1 and domain['eligible_decisions'] == 3
    assert domain['rate'] == pytest.approx(1/3)
    assert domain['candidate']['flips'] == 0
    assert domain['gate']['status'] == 'pass'
    assert report['examples'][0]['log_seqs'] == (1, 2, 3)


def test_changed_required_input_explains_reversal_and_locked_examples_stay_private(tmp_path):
    harness = oscillating_logs(tmp_path, changed_gold=True, mode='silent')
    report = harness.flip_rates(candidate={'unit_weight': 2})
    domain = report['domains']['reference']
    assert domain['flips'] == 0 and domain['explained_reversals'] == 1
    assert domain['explanations']['field:gold'] == 1
    assert report['examples'] == ()


def test_evaluation_includes_flip_aggregates_and_candidate_gate_without_fitting_flips(tmp_path):
    harness = oscillating_logs(tmp_path)
    report = harness.evaluate(candidate={'unit_weight': 2}, bootstrap_draws=20)
    assert report.metrics['flip_rates']['reference']['flips'] == 0
    assert report.gates['flip_rate:reference']['status'] == 'unavailable'  # No holdout with only one game.
    assert 'flip_rates' not in report.gates


def test_missing_intermediate_rounds_do_not_compress_a_long_reversal_into_three_phases(tmp_path):
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='baseline')
    for index, (round_id, name) in enumerate((('4-1', 'middle'), ('5-1', 'last')), 1):
        at = NOW+timedelta(seconds=index)
        raw = log_snapshot(data, at=at, snapshot_id=name)
        raw['round_id'] = round_id
        sessions.append_event('snapshot', raw, timestamp=at.isoformat())
    sessions.end_game(timestamp=(at+timedelta(seconds=1)).isoformat())
    report = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('reference', ('gold',), advice=oscillating_choices),)).flip_rates()
    assert report['domains']['reference']['flips'] == 0
