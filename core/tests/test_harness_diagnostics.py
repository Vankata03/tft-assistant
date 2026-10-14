"""Advice-change reports through logged games and the public harness boundary."""
from datetime import timedelta

import pytest

from tests.test_replay_contracts import NOW, ROOT, logged_game, log_snapshot
from tft_engine import Advice, DomainHook, ScoredOption
from tft_harness import EvaluationHarness


def diagnostic_choices(context):
    selected = 'b' if context.data.tunables['unit_weight'].value > 1 and context.snapshot.field('gold') > 10 else 'a'
    return (Advice('augment', 'Pick '+selected, 'act_this_phase', .9, 'synthetic-diagnostic',
        decision_id=context.snapshot.snapshot_id+':augment', option_id=selected,
        options=(ScoredOption('a', 'pick', {'augment_id': 'A'}, 3.1),
                 ScoredOption('b', 'pick', {'augment_id': 'B'}, 4.2))),)


def test_harness_advice_diff_aligns_original_log_points_and_ranks_changed_choices(tmp_path):
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='baseline')
    at = NOW+timedelta(seconds=1)
    raw = log_snapshot(data, at=at, snapshot_id='second', gold=8)
    sessions.append_event('snapshot', raw, timestamp=at.isoformat())
    sessions.end_game(timestamp=(at+timedelta(seconds=1)).isoformat())
    original = store.get(data.snapshot_id)
    harness = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('augment', (), advice=diagnostic_choices, dependency_fields=('gold',)),))
    report = harness.advice_diff({'unit_weight': 2})
    assert report['eligible_decisions'] == 4
    assert report['changed_decisions'] == 1
    assert report['changed_share'] == .25
    assert report['excluded'] == {}
    assert len(report['largest_changes']) == 1
    change = report['largest_changes'][0]
    assert change['game_id'] == '901' and change['log_seq'] == 1
    assert change['decision'] == 'augment'
    assert change['accepted_choice'] == 'a' and change['candidate_choice'] == 'b'
    assert change['expected_placement_difference'] == pytest.approx(1.1)
    assert report['status'] == 'report_only'
    assert store.get(data.snapshot_id) == original


def information_choices(context):
    return (Advice('reference', 'High' if context.data.tunables['unit_weight'].value > 1 else 'Low',
        'information', .9, 'synthetic-diagnostic'),)


def test_harness_advice_diff_detects_changed_advice_without_scored_options(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, mode='baseline')
    report = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('reference', (), advice=information_choices),)).advice_diff({'unit_weight': 2})
    assert report['changed_decisions'] == 1
    change = report['largest_changes'][0]
    assert change['decision'] == 'reference'
    assert change['expected_placement_difference'] is None


def test_harness_advice_diff_keeps_locked_game_changes_aggregate_only(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path, mode='silent')
    report = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('reference', (), advice=information_choices),)).advice_diff({'unit_weight': 2})
    assert report['changed_decisions'] == 1
    assert report['eligible_decisions'] == 2
    assert report['largest_changes'] == ()
    with pytest.raises(TypeError):
        report['changed_decisions'] = 0


@pytest.mark.parametrize('limit', [-1, 101, True, 1.5])
def test_harness_advice_diff_rejects_unbounded_or_nonintegral_examples(tmp_path, limit):
    sessions, store, _, _ = logged_game(tmp_path)
    with pytest.raises(ValueError, match='limit'):
        EvaluationHarness(sessions, store, repository=ROOT).advice_diff({'unit_weight': 2}, limit=limit)
