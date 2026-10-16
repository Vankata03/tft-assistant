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
    # No timeline point carries follow attribution, so every follow-based split says so.
    for name in ('follow_ignore_placement', 'positioning_residual'):
        assert {row['reason'] for row in diagnostics[name].values()} == {'follow_attribution_unavailable'}
    assert {row['reason'] for row in diagnostics['expected_placement_by_follow_rate'].values()} == {
        'follow_attribution_unavailable'}
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


def outcome_game(tmp_path, *, placement=None, events=(), tunables=None):
    """A finished set-18 ranked capture whose late Riot match truth is recorded separately."""
    import tomllib
    import tomli_w
    from tft_core.storage import SessionStore
    from tests.test_replay_contracts import historical_data, GuideFeed

    store, data = historical_data(tmp_path)
    if tunables:
        path = tmp_path/'patch'/'tunables.toml'
        config = tomllib.loads(path.read_text())
        for name, value in tunables.items():
            config['fields'][name]['value'] = value
        path.write_text(tomli_w.dumps(config))
        data = store.refresh(path.parent, now=NOW+timedelta(microseconds=1), sources=(GuideFeed(),)).snapshot
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.set_mode('baseline')
    sessions.start_game('901', set_id='18', queue_id=1100, patch=data.patch,
        data_snapshot_id=data.snapshot_id, timestamp=NOW.isoformat())
    sessions.append_event('snapshot', log_snapshot(data), timestamp=NOW.isoformat())
    for kind, payload, at in (events(data) if callable(events) else events):
        sessions.append_event(kind, payload, timestamp=at.isoformat())
    sessions.end_game(placement=placement, timestamp=(NOW+timedelta(seconds=30)).isoformat())
    return sessions, store, data


def test_expected_placement_uses_match_outcome_when_the_log_has_no_placement(tmp_path):
    from tests.test_outcomes import match_fixture

    sessions, store, _ = outcome_game(tmp_path)
    harness = EvaluationHarness(sessions, store, repository=ROOT)
    assert harness.evaluate().metrics['expected_placement_mae']['excluded'] == {'terminal_placement_unavailable': 1}
    sessions.record_outcome('901', match_fixture(), owner_puuid='owner')
    report = harness.evaluate()
    row = next(row for row in report.examples if row['metric'] == 'expected_placement_mae')
    assert row['truth'] == 4 and row['truth_source'] == 'riot_match'
    assert report.manifest[0]['truth_sources'] == ('capture_log', 'riot_match')



def eliminated_rival_game(tmp_path, *, simultaneous=False):
    """Seven certified opponents; the scouted rival alone leaves the lobby next."""
    lobby = {'rival': {'hp': 40}}|{f'other-{index}': {'hp': 60} for index in range(6)}
    after = dict(lobby)|{'rival': {'hp': 0}}
    if simultaneous:
        after['other-0'] = {'hp': 0}
    sighting = {'opponent_id': 'rival', 'round_id': '3-2', 'level': 1, 'traits': {}, 'hidden_traits': 0}
    events = lambda data: [('sighting', sighting, NOW+timedelta(seconds=1))]+[
        ('snapshot', log_snapshot(data, at=stamp, snapshot_id=f'lobby-{index}', lobby=players), stamp)
        for index, (stamp, players) in enumerate(((NOW+timedelta(seconds=2), lobby), (NOW+timedelta(seconds=5), after)))]
    return outcome_game(tmp_path, tunables={'opponent_inference_state_cap': 1000}, events=events)


def rival_match(units):
    from tests.test_outcomes import match_fixture
    match = match_fixture()
    match['info']['participants'][7]['units'] = [{'character_id': unit, 'tier': 1, 'items': []} for unit in units]
    return match


def test_opponent_board_scores_last_stage_inference_against_uniquely_joined_final_board(tmp_path):
    sessions, store, _ = eliminated_rival_game(tmp_path)
    harness = EvaluationHarness(sessions, store, repository=ROOT)
    assert harness.evaluate().metrics['opponent_board_brier']['excluded'] == {'match_outcome_unavailable': 1}
    sessions.record_outcome('901', rival_match(['unit', 'TFT18_Ghost']), owner_puuid='owner')
    report = harness.evaluate()
    metric = report.metrics['opponent_board_brier']
    # Inference holds the fixture unit with certainty; the final board adds one unseen unit.
    assert metric['value'] == .5 and metric['eligible_rows'] == 1
    assert metric['status'] == 'report_only'
    row = next(row for row in report.examples if row['metric'] == 'opponent_board_brier')
    assert row['opponent_id'] == 'rival' and row['final_placement'] == 8
    assert row['join'] == 'unique_observed_elimination'
    assert 'opponent_board_brier' not in report.gates
    json.dumps(report.to_dict(), allow_nan=False)


def test_opponent_board_never_joins_simultaneous_eliminations(tmp_path):
    sessions, store, _ = eliminated_rival_game(tmp_path, simultaneous=True)
    sessions.record_outcome('901', rival_match(['unit']), owner_puuid='owner')
    metric = EvaluationHarness(sessions, store, repository=ROOT).evaluate().metrics['opponent_board_brier']
    assert metric['eligible_rows'] == 0
    assert metric['excluded'] == {'elimination_order_not_unique': 1}


def test_opponent_board_never_joins_an_elimination_sharing_its_round_with_another(tmp_path):
    """Capture order inside one round does not prove Riot's within-round placement."""
    lobby = {'rival': {'hp': 40}}|{f'other-{index}': {'hp': 60} for index in range(6)}
    first = dict(lobby)|{'rival': {'hp': 0}}
    second = dict(first)|{'other-0': {'hp': 0}}
    sighting = {'opponent_id': 'rival', 'round_id': '3-2', 'level': 1, 'traits': {}, 'hidden_traits': 0}
    events = lambda data: [('sighting', sighting, NOW+timedelta(seconds=1))]+[
        ('snapshot', log_snapshot(data, at=NOW+timedelta(seconds=2+index), snapshot_id=f'lobby-{index}', lobby=players),
            NOW+timedelta(seconds=2+index)) for index, players in enumerate((lobby, first, second))]
    sessions, store, _ = outcome_game(tmp_path, tunables={'opponent_inference_state_cap': 1000}, events=events)
    sessions.record_outcome('901', rival_match(['unit']), owner_puuid='owner')
    metric = EvaluationHarness(sessions, store, repository=ROOT).evaluate().metrics['opponent_board_brier']
    assert metric['eligible_rows'] == 0
    assert metric['excluded'] == {'same_round_elimination_order_ambiguous': 1}


def test_opponent_board_never_joins_when_last_stage_alive_is_unobserved(tmp_path):
    """A lobby window spanning a stage boundary leaves the last stage alive unknown."""
    lobby = {'rival': {'hp': 40}}|{f'other-{index}': {'hp': 60} for index in range(6)}
    after = dict(lobby)|{'rival': {'hp': 0}}
    sighting = {'opponent_id': 'rival', 'round_id': '3-2', 'level': 1, 'traits': {}, 'hidden_traits': 0}

    def events(data):
        later = log_snapshot(data, at=NOW+timedelta(seconds=5), snapshot_id='lobby-1', lobby=after)
        later['round_id'] = '4-3'
        return [('sighting', sighting, NOW+timedelta(seconds=1)),
            ('snapshot', log_snapshot(data, at=NOW+timedelta(seconds=2), snapshot_id='lobby-0', lobby=lobby),
                NOW+timedelta(seconds=2)), ('snapshot', later, NOW+timedelta(seconds=5))]
    sessions, store, _ = outcome_game(tmp_path, tunables={'opponent_inference_state_cap': 1000}, events=events)
    sessions.record_outcome('901', rival_match(['unit']), owner_puuid='owner')
    metric = EvaluationHarness(sessions, store, repository=ROOT).evaluate().metrics['opponent_board_brier']
    assert metric['eligible_rows'] == 0
    assert metric['excluded'] == {'last_stage_alive_ambiguous': 1}


def test_opponent_board_never_joins_a_placement_whose_match_round_is_shared(tmp_path):
    """Riot's own last_round, when present, also exposes a same-round elimination."""
    sessions, store, _ = eliminated_rival_game(tmp_path)
    match = rival_match(['unit'])
    match['info']['participants'][6]['last_round'] = match['info']['participants'][7]['last_round']
    sessions.record_outcome('901', match, owner_puuid='owner')
    metric = EvaluationHarness(sessions, store, repository=ROOT).evaluate().metrics['opponent_board_brier']
    assert metric['eligible_rows'] == 0
    assert metric['excluded'] == {'same_round_elimination_order_ambiguous': 1}


def test_follow_based_reports_consume_review_attribution_from_logged_display_and_pick(tmp_path):
    from tests.test_review_attribution import _decision_id, _hook, log_delivery, log_pick, log_shown

    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='live')
    decision = _decision_id(sessions, store)
    log_delivery(sessions, decision_id=decision, option_id='a')
    log_shown(sessions, decision_id=decision, option_id='a')
    log_pick(sessions, 'A', 0)
    sessions.end_game(placement=3, timestamp=(NOW+timedelta(seconds=2)).isoformat())
    report = EvaluationHarness(sessions, store, repository=ROOT, hooks=_hook()).evaluate()
    diagnostics = report.metrics['report_only']
    assert diagnostics['follow_attributed_points'] == 1 and diagnostics['follow_rate_games'] == 1
    followed = diagnostics['follow_ignore_placement']
    assert followed['followed']['value'] == 3 and followed['followed']['eligible_rows'] == 1
    assert followed['ignored']['value'] is None and followed['ignored']['reason'] == 'no_eligible_truth'
    by_rate = diagnostics['expected_placement_by_follow_rate']
    assert by_rate['high']['eligible_rows'] == report.metrics['expected_placement_mae']['eligible_rows'] > 0
    assert by_rate['low']['reason'] == 'no_eligible_truth'


def anti_dive_layout(context):
    from tft_engine import Advice
    return (Advice('positioning', 'Move', 'act_this_phase', .9, 'fixture', option_id='positioning:layout',
        payload={'operation': 'layout', 'layout': [{'unit_index': 0, 'unit_id': 'unit', 'cell': 1}],
            'adjustments': {'anti_dive': True, 'anti_aoe': False}}),)


def test_positioning_residual_splits_active_anti_dive_fights_by_attributed_follow(tmp_path):
    import tomllib
    import tomli_w
    from tft_core.storage import SessionStore
    from tft_engine import Board, DomainHook, Unit
    from tests.test_replay_contracts import historical_data
    from tests.test_review_attribution import _decision_id, log_delivery, log_shown

    store, _ = historical_data(tmp_path)
    path = tmp_path/'patch'/'static.toml'
    static = tomllib.loads(path.read_text())
    static['fields']['round_types']['value']['3-2'] = 'combat'
    path.write_text(tomli_w.dumps(static))
    data = store.refresh(path.parent, now=NOW+timedelta(microseconds=1)).snapshot
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.set_mode('live')
    sessions.start_game('901', set_id='18', patch=data.patch, data_snapshot_id=data.snapshot_id,
        timestamp=NOW.isoformat())
    sessions.append_event('snapshot', log_snapshot(data), timestamp=NOW.isoformat())
    hooks = (DomainHook('positioning', (), advice=anti_dive_layout),)
    decision = _decision_id(sessions, store, decision='positioning', hooks=hooks)
    log_delivery(sessions, decision_id=decision, option_id='positioning:layout', domain='positioning')
    log_shown(sessions, decision_id=decision, option_id='positioning:layout')
    # A fresh unchanged read after the display fixes the player's onset after it.
    unchanged = NOW+timedelta(seconds=.5)
    sessions.append_event('snapshot', log_snapshot(data, at=unchanged, snapshot_id='unchanged'),
        timestamp=unchanged.isoformat())
    at = NOW+timedelta(seconds=1)
    sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id='moved',
        board=Board((Unit('unit', position=1),))), timestamp=at.isoformat())
    sessions.append_event('fight_start', {'round_id': '3-2', 'opponent_id': 'rival'},
        timestamp=(at+timedelta(seconds=.1)).isoformat())
    sessions.append_event('fight_result', {'round_id': '3-2', 'opponent_id': 'rival', 'result': 'loss', 'hp_lost': 5},
        timestamp=(at+timedelta(seconds=1)).isoformat())
    sessions.end_game(timestamp=(at+timedelta(seconds=2)).isoformat())
    report = EvaluationHarness(sessions, store, repository=ROOT, hooks=hooks).evaluate()
    residual = report.metrics['report_only']['positioning_residual']
    forecast = next(row for row in report.examples if row['metric'] == 'fight_brier')
    assert residual['followed']['eligible_rows'] == 1
    assert residual['followed']['value'] == forecast['prediction']-0
    assert residual['ignored']['reason'] == 'no_eligible_truth'
