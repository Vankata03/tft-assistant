"""Outcome calibration through logged captures and the public evaluation boundary."""
from datetime import timedelta
import json

import pytest

from tft_harness import EvaluationHarness
from tests.test_replay_contracts import NOW, ROOT, logged_game, log_snapshot


def test_expected_placement_uses_terminal_truth_and_fresh_complete_hp_rank(tmp_path):
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='baseline')
    sessions.end_game(placement=4, timestamp=(NOW+timedelta(seconds=4)).isoformat())
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    metric = report.metrics['expected_placement_mae']
    assert metric['eligible_rows'] == 1
    assert metric['value'] == 3  # The fixture's gold-rich selected Line clips to placement 1.
    assert metric['naive']['value'] == 2  # Own 73 HP ranks second behind the certified alive rival.
    row = next(row for row in report.examples if row['metric'] == 'expected_placement_mae')
    assert row['truth'] == 4 and row['naive_prediction'] == 2
    assert row['truth_source'] == 'game_end'
    json.dumps(report.to_dict(), allow_nan=False)


def test_expected_placement_excludes_partial_games_and_does_not_impute_missing_hp_rank(tmp_path):
    sessions, store, data, _ = logged_game(tmp_path, finish=False, mode='baseline')
    at = NOW+timedelta(seconds=1)
    raw = log_snapshot(data, at=at, snapshot_id='incomplete', lobby_complete=False)
    sessions.append_event('snapshot', raw, timestamp=at.isoformat())
    sessions.end_game(placement=4, timestamp=(at+timedelta(seconds=1)).isoformat())
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    metric = report.metrics['expected_placement_mae']
    assert metric['eligible_rows'] == 1
    assert metric['excluded']['fresh_complete_hp_rank_unavailable'] == 1


def test_line_residual_joins_end_of_horizon_to_next_round_and_stays_out_of_gates(tmp_path):
    import tomllib
    import tomli_w
    from tft_core.storage import SessionStore
    from tests.test_replay_contracts import historical_data, GuideFeed

    store, _ = historical_data(tmp_path)
    path = tmp_path/'patch'/'static.toml'
    config = tomllib.loads(path.read_text())
    config['fields']['round_order']['value'] = ['1-1', '3-1', '3-2', '4-1', '5-1', '6-1']
    config['fields']['level_calendar']['value'] = {'1-1': 1, '3-2': 1, '4-1': 1}
    path.write_text(tomli_w.dumps(config))
    refreshed = store.refresh(path.parent, now=NOW+timedelta(seconds=1), sources=(GuideFeed(),))
    assert refreshed.error is None
    data = refreshed.snapshot
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.set_mode('baseline')
    sessions.start_game('901', set_id='18', patch=data.patch, data_snapshot_id=data.snapshot_id,
        timestamp=NOW.isoformat())
    for index, (round_id, gold, hp, level) in enumerate([
        ('3-2', 18, 73, 1), ('4-1', 24, 73, 2), ('5-1', 30, 70, 2)]):
        at = NOW+timedelta(seconds=index)
        raw = log_snapshot(data, at=at, snapshot_id=f'round-{index}', gold=gold, hp=hp, level=level)
        raw['round_id'] = round_id
        sessions.append_event('snapshot', raw, timestamp=at.isoformat())
    sessions.end_game(placement=4, timestamp=(at+timedelta(seconds=1)).isoformat())
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate(candidate={'fight_scale': 0})
    assert report.metrics['line_gold_mae']['value'] == 1
    assert report.metrics['line_level_mae']['value'] == 0
    assert report.metrics['line_hp_mae']['value'] == 3
    assert not {'line_gold_mae', 'line_level_mae', 'line_hp_mae'} & report.gates.keys()
    row = next(row for row in report.examples if row['metric'] == 'line_gold_mae')
    assert row['horizon_round_id'] == '4-1' and row['truth_round_id'] == '5-1'
    assert row['policy_status'] == 'unconfirmed'
    assert report.metrics['line_gold_mae']['status'] == 'report_only'


def test_current_set_filter_is_independent_from_previous_patch_static_flag(tmp_path):
    sessions, store, data, _ = logged_game(tmp_path, mode='baseline')
    for game_id, set_id, previous_patch in [('902', '17', False), ('903', '18', True)]:
        at = NOW+timedelta(days=int(game_id)-901)
        sessions.start_game(game_id, set_id=set_id, patch=data.patch, data_snapshot_id=data.snapshot_id,
            previous_patch=previous_patch, timestamp=at.isoformat())
        raw = log_snapshot(data, at=at)
        raw['game_id'] = game_id
        sessions.append_event('snapshot', raw, timestamp=at.isoformat())
        sessions.end_game(placement=4, timestamp=(at+timedelta(seconds=1)).isoformat())
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    assert report.counts['excluded_other_set_games'] == 1
    assert report.counts['previous_patch_games'] == 1
    assert {row['game_id'] for row in report.manifest} == {'901', '903'}
    assert next(row for row in report.manifest if row['game_id'] == '903')['previous_patch'] is True
    assert report.provenance['current_set'] == '18'
    assert report.metrics['previous_patch_split']['previous_patch_static']['expected_placement_mae']['eligible_rows'] == 1


def test_report_only_calibration_uses_game_weights_and_never_enters_fit_or_gates(tmp_path):
    from tests.test_harness import combat_logs

    sessions, store = combat_logs(tmp_path, results=('loss', 'draw'))
    harness = EvaluationHarness(sessions, store, repository=ROOT)
    report = harness.evaluate(candidate={'fight_scale': 0}, bootstrap_draws=20)
    diagnostics = report.metrics['report_only']
    curve = diagnostics['calibration_by_stage']['3'][0]
    assert curve['prediction'] == .5 and curve['truth'] == 0
    assert curve['eligible_rows'] == 1 and curve['eligible_games'] == 1
    assert diagnostics['gap_share'] == 0
    assert diagnostics['follow_ignore_placement']['followed']['value'] is None
    assert 'report_only' not in report.gates
    with pytest.raises(ValueError, match='Report-only'):
        harness.fit({'fight_scale': [1]}, metric='line_gold_mae')
    json.dumps(report.to_dict(), allow_nan=False)


def test_hit_probability_does_not_treat_engine_target_or_pinned_line_as_confirmed_player_goals(tmp_path):
    sessions, store, _, _ = logged_game(tmp_path)
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    metric = report.metrics['hit_log_loss']
    assert metric['eligible_rows'] == 0
    assert metric['excluded']['confirmed_player_goals_unavailable'] == 1


def natural_shop_game(tmp_path, *, paid_roll=False):
    import tomllib
    import tomli_w
    from tft_core.storage import SessionStore
    from tft_engine import Board, Unit
    from tests.test_replay_contracts import historical_data, GuideFeed

    store, _ = historical_data(tmp_path)
    path = tmp_path/'patch'/'static.toml'
    config = tomllib.loads(path.read_text())
    config['fields']['round_order']['value'] = ['1-1', '3-1', '3-2', '4-1', '5-1', '6-1']
    path.write_text(tomli_w.dumps(config))
    refreshed = store.refresh(path.parent, now=NOW+timedelta(seconds=1), sources=(GuideFeed(),))
    assert refreshed.error is None
    data = refreshed.snapshot
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.set_mode('baseline')
    sessions.start_game('901', set_id='18', patch=data.patch, data_snapshot_id=data.snapshot_id,
        timestamp=NOW.isoformat())
    for index, (round_id, gold, stars, shop) in enumerate([
        ('3-2', 18, 1, []), ('4-1', 24, 1, [{'slot': i, 'unit_id': 'unit', 'cost': 1} for i in range(5)]),
        ('4-1', 22, 2, []), ('5-1', 29, 2, [])]):
        at = NOW+timedelta(seconds=index)
        if index == 2:
            for slot in range(2):
                sessions.append_event('purchase', {'unit_id': 'unit', 'slot': slot, 'cost': 1, 'copies': 1},
                    timestamp=at.isoformat())
            if paid_roll:
                sessions.append_event('roll', {'cost': 2, 'round_id': '4-1'}, timestamp=at.isoformat())
        raw = log_snapshot(data, at=at, snapshot_id=f'roll-policy-{index}', gold=gold, level=10,
            board=Board((Unit('unit', stars=stars),)), shop=shop, comp_lock='guide',
            remaining_effects=[], remaining_effects_complete=True, held_augments=[], held_augments_complete=True)
        raw['round_id'] = round_id
        sessions.append_event('snapshot', raw, timestamp=at.isoformat())
    sessions.end_game(placement=4, timestamp=(at+timedelta(seconds=1)).isoformat())
    return sessions, store


def test_hit_log_loss_rebuilds_shop_chain_for_identifiable_natural_shop_policy(tmp_path):
    sessions, store = natural_shop_game(tmp_path)
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    metric = report.metrics['hit_log_loss']
    assert metric['eligible_rows'] == 1
    assert metric['value'] == 0 and metric['naive']['value'] == 0
    row = next(row for row in report.examples if row['metric'] == 'hit_log_loss')
    assert row['truth'] == 1
    assert row['naive_source'] == 'tft_engine.shop_math.hit_probability'
    assert row['policy_status'] == 'confirmed_no_paid_rolls'
    assert row['shops'] == 1 and row['slots'] == 5 and row['level'] == 10


def test_paid_roll_without_confirmed_stopping_floor_is_not_scored_as_a_hit(tmp_path):
    sessions, store = natural_shop_game(tmp_path, paid_roll=True)
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    metric = report.metrics['hit_log_loss']
    assert metric['eligible_rows'] == 0
    assert metric['excluded']['paid_roll_stopping_policy_unidentifiable'] >= 1


def test_partial_games_leave_placement_calibration_but_keep_qualified_fights(tmp_path):
    from tests.test_harness import combat_logs

    sessions, store = combat_logs(tmp_path, results=('loss',), extra_fight=True, gap=True)
    # One of two known rounds is retrospectively invalidated; the later fight remains usable.
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    assert report.counts['partial_games'] == 1
    assert report.metrics['expected_placement_mae']['value'] is None
    assert report.metrics['expected_placement_mae']['excluded']['partial_game_over_25_percent_gaps'] == 1
    assert report.metrics['fight_brier']['eligible_rows'] == 1
