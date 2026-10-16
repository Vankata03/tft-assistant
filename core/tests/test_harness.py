"""Evaluation consumes real logs and predicts before observing fixture outcomes."""
from datetime import timedelta
import tomllib

import tomli_w

from tft_core.storage import SessionStore
from tests.test_replay_contracts import NOW, ROOT, historical_data, log_snapshot


def combat_logs(tmp_path, *, results=('loss', 'draw'), gap=False, buff_power=None, extra_fight=False,
                extra_game_index=0, stars_by_game=None, slot_budget=None, unit_slots=None):
    store, data = historical_data(tmp_path)
    path = tmp_path/'patch'/'static.toml'
    static = tomllib.loads(path.read_text())
    static['fields']['round_types']['value']['3-2'] = 'combat'
    if slot_budget is not None:
        static['fields']['team_capacity']['value']['levels']['1'] = slot_budget
    if unit_slots is not None:
        import json
        entities_path = tmp_path/'patch'/'entities.json'
        entities = json.loads(entities_path.read_text())
        entities['entities'][0]['values']['team_slot_cost']['value'] = unit_slots
        entities_path.write_text(json.dumps(entities))
    if extra_fight:
        static['fields']['round_types']['value']['3-3'] = 'combat'
    if buff_power is not None:
        static['fields']['wisps']['value'] = {'buff': {'effect_kind': 'combat_buff',
            'cost': 1, 'offer_stages': [3], 'values': {'buff_id': 'strong'}}}
        static['fields']['combat_buff_power']['value'] = {'strong': buff_power}
    path.write_text(tomli_w.dumps(static))
    data = store.refresh(path.parent, now=NOW+timedelta(seconds=1)).snapshot
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.set_mode('silent')
    for index, result in enumerate(results):
        game_id = str(901+index)
        at = NOW+timedelta(days=index)
        sessions.start_game(game_id, set_id='18', patch=data.patch, data_snapshot_id=data.snapshot_id,
            timestamp=at.isoformat())
        changes = {} if buff_power is None else {'remaining_effects': [
            {'effect_id': 'buff', 'source_kind': 'wisp', 'remaining_rounds': 1}],
            'remaining_effects_complete': True}
        if stars_by_game and index in stars_by_game:
            from tft_engine import Board, Unit
            changes['board'] = Board((Unit('unit', stars=stars_by_game[index]),))
        snapshot = log_snapshot(data, at=at, snapshot_id=game_id+'-initial', **changes) | {'game_id': game_id}
        sessions.append_event('snapshot', snapshot, timestamp=at.isoformat())
        sessions.append_event('fight_start', {'round_id': '3-2', 'opponent_id': 'rival', 'hp_before': 73},
            timestamp=(at+timedelta(seconds=1)).isoformat())
        sessions.append_event('fight_result', {'round_id': '3-2', 'opponent_id': 'rival',
            'hp_before': 73, 'hp_after': 68 if result == 'loss' else 73,
            'hp_lost': 5 if result == 'loss' else 0, 'result': result},
            timestamp=(at+timedelta(seconds=10)).isoformat())
        if gap:
            sessions.append_event('capture_gap', {'start': at.isoformat(),
                'end': (at+timedelta(seconds=2)).isoformat(), 'reason': 'fixture interrupted capture'},
                timestamp=(at+timedelta(seconds=11)).isoformat())
        if extra_fight and index == extra_game_index:
            from tft_engine import Board, Unit
            observed_at = at+timedelta(seconds=11)
            stronger = log_snapshot(data, at=observed_at, snapshot_id=game_id+'-next',
                board=Board((Unit('unit', stars=3),)), level=2, hp=68) | {'game_id': game_id, 'round_id': '3-3'}
            sessions.append_event('snapshot', stronger, timestamp=observed_at.isoformat())
            sessions.append_event('fight_start', {'round_id': '3-3', 'opponent_id': 'rival', 'hp_before': 68},
                timestamp=(at+timedelta(seconds=12)).isoformat())
            sessions.append_event('fight_result', {'round_id': '3-3', 'opponent_id': 'rival',
                'hp_before': 68, 'hp_after': 68, 'hp_lost': 0, 'result': 'win'},
                timestamp=(at+timedelta(seconds=21)).isoformat())
        sessions.end_game(placement=4, timestamp=(at+timedelta(seconds=22)).isoformat())
    return sessions, store


def test_harness_scores_actual_public_predictions_excludes_draw_and_suppresses_locked_examples(tmp_path):
    from tft_harness import EvaluationHarness

    sessions, store = combat_logs(tmp_path)
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    assert report.metrics['fight_brier']['value'] == .25
    assert report.metrics['fight_brier']['eligible_rows'] == 1
    assert report.metrics['fight_brier']['eligible_games'] == 1
    assert report.metrics['fight_brier']['excluded']['draw_not_bernoulli'] == 1
    assert report.metrics['damage_mae']['value'] == .5  # 4 stage base + .5 survivor versus 5 observed.
    assert report.metrics['damage_mae']['naive']['value'] == 1
    assert report.counts['locked_games'] == 2
    assert report.examples == ()
    assert report.gates['fight_brier']['status'] == 'unavailable'
    assert report.gates['fight_brier']['reason'] == 'insufficient_holdout_games'
    assert report.to_dict()['schema_version'] == 1


def test_gap_invalidates_all_metrics_at_the_point_and_keeps_missing_counts_visible(tmp_path):
    from tft_harness import EvaluationHarness

    sessions, store = combat_logs(tmp_path, results=('loss',), gap=True)
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    assert report.metrics['fight_brier']['value'] is None
    assert report.metrics['fight_brier']['excluded']['capture_gap'] == 1
    assert report.metrics['damage_mae']['value'] is None
    assert report.counts['partial_games'] == 1
    assert report.counts['known_rounds'] == 1
    assert report.counts['gap_rounds'] == 1


def test_harness_and_review_share_captured_one_round_power_prediction(tmp_path):
    import pytest
    from tft_harness import EvaluationHarness
    from tft_review import ReplayProducer, ReviewPolicy

    sessions, store = combat_logs(tmp_path, results=('loss',), buff_power=10)
    batch = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    review = ReviewPolicy(min_cost=.05).build(batch, data=store.get(batch.identity['data_snapshot_id']))
    assert review.fights[0]['win_probability'] == pytest.approx(.9999546021312976)
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    assert report.metrics['fight_brier']['value'] == pytest.approx(.9999092063235617)
    assert report.metrics['damage_mae']['value'] == pytest.approx(.9999546021312976)


def test_impossible_probability_is_a_retained_hard_miss_in_finite_report_not_silently_dropped(tmp_path):
    import json
    from tft_harness import EvaluationHarness

    sessions, store = combat_logs(tmp_path, results=('loss',), buff_power=1000)
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    metric = report.metrics['fight_log_loss']
    assert metric['eligible_rows'] == 1 and metric['eligible_games'] == 1
    assert metric['value'] is None and metric['reason'] == 'infinite_log_loss'
    assert metric['hard_misses'] == 1
    assert report.metrics['fight_brier']['value'] == 1
    json.dumps(report.to_dict(), allow_nan=False)


def test_metric_aggregation_weights_games_equally_instead_of_repeated_fights(tmp_path):
    import pytest
    from tft_harness import EvaluationHarness

    sessions, store = combat_logs(tmp_path, results=('loss', 'loss'), extra_fight=True)
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate()
    metric = report.metrics['fight_brier']
    assert metric['eligible_rows'] == 3 and metric['eligible_games'] == 2
    assert metric['value'] == pytest.approx(.19105233415465275)
    assert report.provenance['metric_weighting'] == 'equal games; mean eligible rows within each game'


def test_holdout_gates_pair_whole_games_and_retain_historical_pins(tmp_path):
    from tft_harness import EvaluationHarness

    sessions, store = combat_logs(tmp_path, results=('loss',)*10, extra_fight=True)
    before = store.get(sessions.list_games()[0]['data_snapshot_id'])
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate(
        candidate={'fight_scale': 0}, bootstrap_seed=7, bootstrap_draws=200)
    gate = report.gates['fight_brier']
    assert gate['sample_unit'] == 'game'
    assert gate['eligible_game_ids'] == ('909', '910')
    assert gate['bootstrap_draws'] == 200 and gate['bootstrap_seed'] == 7
    assert gate['interval_convention'] == 'percentile95; nearest-rank 2.5 and 97.5'
    assert gate['candidate_minus_accepted']['value'] == 0
    assert gate['candidate_minus_accepted']['lower'] == gate['candidate_minus_accepted']['upper'] == 0
    assert gate['candidate_minus_accepted']['reason'] is None
    assert gate['no_regression']['status'] == 'pass'
    assert gate['beats_naive']['status'] == 'fail'
    assert gate['status'] == 'fail' # An unchanged candidate is not a regression; it does not beat the stage baseline.
    assert report.provenance['training_game_ids'] == tuple(str(game) for game in range(901, 909))
    assert store.get(before.snapshot_id) == before  # No refreshed data or candidate publication.


def test_informative_paired_bootstrap_keeps_multiple_fights_in_their_whole_game(tmp_path):
    import pytest
    from math import exp
    from tft_harness import EvaluationHarness

    sessions, store = combat_logs(tmp_path, results=('win','loss')*5, extra_fight=True,
        extra_game_index=8, stars_by_game={9:3})
    report = EvaluationHarness(sessions, store, repository=ROOT).evaluate(
        candidate={'fight_scale':0}, bootstrap_seed=19, bootstrap_draws=1000)
    probability = 1/(1+exp(-2))
    first_game = (.25-(1-probability)**2)/2 # unchanged first fight and changed second fight.
    second_game = .25-probability**2
    difference = report.gates['fight_brier']['candidate_minus_accepted']
    assert difference['reason'] is None
    assert difference['value'] == pytest.approx((first_game+second_game)/2)
    assert difference['lower'] == pytest.approx(second_game)
    assert difference['upper'] == pytest.approx(first_game)
    assert report.gates['fight_brier']['eligible_game_ids'] == ('909','910')
    assert report.examples == () # Both private game rows remain suppressed while locked.


def test_shared_prefight_damage_uses_physical_units_instead_of_level_or_slots(tmp_path):
    import pytest
    from math import exp
    from tft_review import ReplayProducer, ReviewPolicy

    sessions, store = combat_logs(tmp_path, results=('loss',), slot_budget=4, unit_slots=2)
    batch = ReplayProducer(sessions, store, repository=ROOT).produce('901')
    report = ReviewPolicy(min_cost=.05).build(batch, data=store.get(batch.identity['data_snapshot_id']))
    fight = report.fights[0]
    assert fight['winner_unit_count'] == 2 # level1's four slots fit two two-slot units.
    assert fight['predicted_hp_loss'] == pytest.approx(4+2/(1+exp(-1)))
