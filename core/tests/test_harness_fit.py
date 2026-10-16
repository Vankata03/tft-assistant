"""Functional fitting changes real predictions and never trains on holdout truth."""
import pytest

from tft_harness import EvaluationHarness
from tests.test_harness import combat_logs
from tests.test_replay_contracts import ROOT


def test_functional_family1_fit_optimizes_training_log_loss_and_freezes_holdout(tmp_path):
    (tmp_path/'first').mkdir()
    (tmp_path/'different-holdout').mkdir()
    sessions, store = combat_logs(tmp_path/'first', results=('win',)*8+('loss',)*2,
        stars_by_game={index:2 for index in range(10)})
    original = store.get(sessions.list_games()[0]['data_snapshot_id'])
    report = EvaluationHarness(sessions,store,repository=ROOT).fit(
        {'fight_scale':[.25,1,2]}, metric='fight_log_loss', bootstrap_seed=11, bootstrap_draws=100)
    assert report.parameters == {'fight_scale':2}
    assert report.training_game_ids == tuple(str(game) for game in range(901,909))
    assert report.holdout_game_ids == ('909','910')
    assert report.training_objective['candidate'] < report.training_objective['reference']
    assert report.training_objective['candidate'] == pytest.approx(.12692801104297263)
    assert report.solver['evaluations'] == 3
    assert report.status == 'unaccepted_candidate'
    assert report.gates['fight_brier']['no_regression']['status'] == 'fail'
    assert store.get(original.snapshot_id) == original
    changed, same_store = combat_logs(tmp_path/'different-holdout', results=('win',)*10,
        stars_by_game={index:2 for index in range(10)})
    second = EvaluationHarness(changed,same_store,repository=ROOT).fit(
        {'fight_scale':[.25,1,2]},metric='fight_log_loss',bootstrap_draws=100)
    assert second.parameters == report.parameters
    assert second.training_objective == report.training_objective


@pytest.mark.parametrize('parameters',[
    {'rollouts_full':[4,8]}, {'review_min_cost':[.05,.1]}, {'unit_prior_strength':[1,2]},
    {'opponent_growth_curve':[{}]}, {'fight_scale':[1,2],'unit_weight':[1,2]},
])
def test_fit_rejects_other_families_and_unidentified_scale_before_any_candidate(parameters,tmp_path):
    sessions,store = combat_logs(tmp_path,results=('loss','win'))
    with pytest.raises(ValueError,match='family 1|normalization'):
        EvaluationHarness(sessions,store,repository=ROOT).fit(parameters)


def staged_logs(tmp_path, games, *, set_ids=None):
    """Logged games of (round_id, result[, own stars]) fights with prefight snapshots.

    Own stars default to 2; zero stars logs an empty board.
    """
    from datetime import timedelta
    import tomllib
    import tomli_w
    from tft_core.storage import SessionStore
    from tests.test_replay_contracts import NOW, historical_data, log_snapshot
    from tft_engine import Board, Unit

    store, data = historical_data(tmp_path)
    path = tmp_path/'patch'/'static.toml'
    static = tomllib.loads(path.read_text())
    for fights in games:
        for round_id, *_ in fights:
            static['fields']['round_types']['value'][round_id] = 'combat'
    path.write_text(tomli_w.dumps(static))
    data = store.refresh(path.parent, now=NOW+timedelta(seconds=1)).snapshot
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.set_mode('silent')
    for index, fights in enumerate(games):
        game_id, at = str(901+index), NOW+timedelta(days=index)
        sessions.start_game(game_id, set_id=(set_ids or {}).get(index, '18'), patch=data.patch,
            data_snapshot_id=data.snapshot_id, timestamp=at.isoformat())
        for number, (round_id, result, *stars) in enumerate(fights):
            stars = stars[0] if stars else 2
            moment = at+timedelta(seconds=20*number)
            snapshot = log_snapshot(data, at=moment, snapshot_id=f'{game_id}-{number}',
                board=Board((Unit('unit', stars=stars),) if stars else ())) | {
                'game_id': game_id, 'round_id': round_id}
            sessions.append_event('snapshot', snapshot, timestamp=moment.isoformat())
            sessions.append_event('fight_start', {'round_id': round_id, 'opponent_id': 'rival',
                'hp_before': 73}, timestamp=(moment+timedelta(seconds=1)).isoformat())
            sessions.append_event('fight_result', {'round_id': round_id, 'opponent_id': 'rival',
                'hp_before': 73, 'hp_after': 73 if result == 'win' else 68,
                'hp_lost': 0 if result == 'win' else 5, 'result': result},
                timestamp=(moment+timedelta(seconds=10)).isoformat())
        sessions.end_game(placement=4, timestamp=(at+timedelta(hours=1)).isoformat())
    return sessions, store


def test_continuous_family1_fit_reaches_the_training_likelihood_optimum_inside_declared_bounds(tmp_path):
    from math import log
    from tft_harness.fitting import ContinuousRange, fit

    outcomes = ('win', 'loss', 'win', 'win', 'loss', 'win', 'win', 'win', 'loss', 'win')
    sessions, store = staged_logs(tmp_path, [[('3-2', result)] for result in outcomes])
    report = fit(EvaluationHarness(sessions, store, repository=ROOT),
        {'fight_scale': ContinuousRange(.05, 20)}, metric='fight_log_loss',
        bootstrap_seed=3, bootstrap_draws=50, max_evaluations=40)
    # Training holds six wins in eight equal-power fights, so the likelihood
    # optimum predicts exactly .75 and its log loss is the Bernoulli entropy.
    assert report.training_objective['candidate'] == pytest.approx(-(.75*log(.75)+.25*log(.25)), abs=1e-6)
    assert .05 < report.parameters['fight_scale'] < 20
    assert report.solver['method'].startswith('bounded golden-section')
    assert report.solver['evaluations'] <= 40
    assert report.solver['at_bound'] == ()
    assert report.holdout_game_ids == ('909', '910')
    assert set(report.gates) >= {'fight_log_loss'}
    assert report.status == 'unaccepted_candidate'


def test_per_stage_scale_starts_pooled_and_splits_only_past_the_fight_threshold_with_shrinkage(tmp_path):
    from tft_harness.fitting import ContinuousRange, fit

    games = [[('3-2', 'win'), ('3-3', 'win' if index % 4 else 'loss'), ('4-2', 'loss' if index % 3 else 'win')]
        for index in range(10)]
    sessions, store = staged_logs(tmp_path, games)
    report = fit(EvaluationHarness(sessions, store, repository=ROOT),
        {'win_scale_by_stage': ContinuousRange(.05, 20)}, metric='fight_log_loss',
        bootstrap_draws=50, max_evaluations=80, stage_split_min_fights=12)
    stages = report.solver['stages']
    assert stages['3']['fights'] == 16 and stages['3']['split'] is True
    assert stages['4']['fights'] == 8 and stages['4']['split'] is False
    pooled = report.solver['pooled']['win_scale_by_stage']
    scales = report.parameters['win_scale_by_stage']
    assert set(scales) == {str(stage) for stage in range(1, 7)}
    assert scales['4'] == scales['1'] == pooled
    raw = stages['3']['unshrunk']['win_scale_by_stage']
    assert min(raw, pooled) < scales['3'] < max(raw, pooled)
    assert report.solver['shrinkage'] == 'n/(n+12) toward pooled'


def test_fit_uses_only_games_of_the_current_set(tmp_path):
    from tft_harness.fitting import ContinuousRange, fit

    outcomes = ('loss', 'win', 'win', 'loss', 'win', 'win', 'win', 'loss', 'win', 'win', 'win', 'loss')
    sessions, store = staged_logs(tmp_path, [[('3-2', result)] for result in outcomes],
        set_ids={0: '17', 1: '17'})
    report = fit(EvaluationHarness(sessions, store, repository=ROOT),
        {'fight_scale': ContinuousRange(.05, 20)}, bootstrap_draws=50, set_id='18')
    assert report.training_game_ids == tuple(str(game) for game in range(903, 911))
    assert report.holdout_game_ids == ('911', '912')
    assert report.solver['set_id'] == '18'
    with pytest.raises(ValueError, match='set 16'):
        fit(EvaluationHarness(sessions, store, repository=ROOT),
            {'fight_scale': ContinuousRange(.05, 20)}, bootstrap_draws=50, set_id='16')


def test_continuous_ranges_must_be_finite_ordered_and_not_mixed_with_grids(tmp_path):
    from tft_harness.fitting import ContinuousRange, fit

    for bounds in ((2, 1), (0, float('inf')), (1, 2, 3), (True, 2)):
        with pytest.raises(ValueError, match='range'):
            ContinuousRange(*bounds)
    sessions, store = staged_logs(tmp_path, [[('3-2', 'win')], [('3-2', 'loss')]])
    with pytest.raises(ValueError, match='grid'):
        fit(EvaluationHarness(sessions, store, repository=ROOT),
            {'fight_scale': ContinuousRange(1, 2), 'terminal_hp_weight': [1]})


def test_continuous_fit_rejects_report_only_metrics_and_conflicting_harness_set(tmp_path):
    from tft_harness.fitting import ContinuousRange, fit

    sessions, store = staged_logs(tmp_path, [[('3-2', 'win')], [('3-2', 'loss')]])
    with pytest.raises(ValueError, match='Report-only'):
        fit(EvaluationHarness(sessions, store, repository=ROOT),
            {'fight_scale': ContinuousRange(1, 2)}, metric='line_gold_mae')
    with pytest.raises(ValueError, match='current set 17'):
        fit(EvaluationHarness(sessions, store, repository=ROOT, current_set='17'),
            {'fight_scale': ContinuousRange(1, 2)}, set_id='18')


def test_continuous_power_scale_joint_fit_accepts_explicit_fixed_normalization(tmp_path):
    from tft_harness.fitting import ContinuousRange, fit
    sessions, store = staged_logs(tmp_path, [[('3-2', result)] for result in ('win','loss','win','win','loss')])
    report = fit(EvaluationHarness(sessions, store, repository=ROOT),
        {'fight_scale': ContinuousRange(.2, 2), 'trait_weight': ContinuousRange(.2, 2)},
        fixed={'unit_weight': 1.0}, max_evaluations=80, bootstrap_draws=20)
    assert report.solver['fixed']['unit_weight'] == 1


def test_model_uncertainty_refits_game_bootstrap_training_without_holdout(tmp_path):
    from tft_harness.fitting import model_uncertainty
    sessions, store = staged_logs(tmp_path, [[('3-2', result)] for result in
        ('win','loss','win','win','loss')])
    uncertainty = model_uncertainty(EvaluationHarness(sessions, store, repository=ROOT),
        {'fight_scale': [.25,1,2]}, draws=6, seed=17)
    assert uncertainty['method'] == 'training-game bootstrap refits'
    assert len(uncertainty['parameters']) == 6
    assert len({row['fight_scale'] for row in uncertainty['parameters']}) > 1
    assert uncertainty['training_games'] == 4 and uncertainty['holdout_games'] == 1
    assert 'game_id' not in str(uncertainty)


def test_nested_star_mix_simplex_fits_real_opponent_predictions(tmp_path):
    from tft_harness.fitting import SimplexRange, fit
    sessions, store = staged_logs(tmp_path, [[('3-2', result)] for result in
        ('win','loss','win','loss','win','loss','win','loss','win','loss')])
    report = fit(EvaluationHarness(sessions,store,repository=ROOT),
        {'opponent_star_mix': {'1-1': {str(cost): SimplexRange(3,start=(.8,.1,.1)) if cost == 1 else [1,0,0]
            for cost in range(1,6)}}}, max_evaluations=100, bootstrap_draws=20)
    mix = report.parameters['opponent_star_mix']['1-1']['1']
    assert all(0 < p < 1 for p in mix) and sum(mix) == pytest.approx(1.)
    assert report.training_objective['candidate'] < report.training_objective['reference']
    assert report.training_objective['candidate'] == pytest.approx(.69314718056,abs=1e-5)
    assert set(report.solver['ranges']) == {'opponent_star_mix/1-1/1/0','opponent_star_mix/1-1/1/1'}
    assert report.solver['evaluations'] <= 100


def test_nested_prior_maps_preserve_fixed_cells_and_replay_predictions(tmp_path):
    from tft_harness.fitting import ContinuousRange, fit
    sessions, store = staged_logs(tmp_path, [[('3-2', result)] for result in ('win','loss','win','loss','win')])
    report = fit(EvaluationHarness(sessions,store,repository=ROOT), {
        'emblem_count_prior': {'0': ContinuousRange(.2,1,start=1), '1': .1},
        'size_level_prior': {'1': {'1': ContinuousRange(.2,1,start=1), '2': .1}},
    }, max_evaluations=20, bootstrap_draws=20)
    assert report.parameters['emblem_count_prior']['1'] == .1
    assert report.parameters['size_level_prior']['1']['2'] == .1
    assert set(report.solver['ranges']) == {'emblem_count_prior/0','size_level_prior/1/1'}
    assert report.training_objective['candidate'] is not None
    assert report.holdout_game_ids == ('905',)


@pytest.mark.parametrize('arguments', [
    {'size':1}, {'low':0,'high':float('inf')}, {'start':(1.,0.,0.)},
    {'start':(.2,.2,.2)}, {'low':-.1,'high':.1,'start':(.8,.1,.1)},
])
def test_simplex_ranges_require_finite_identifiable_domains(arguments):
    from tft_harness.fitting import SimplexRange
    with pytest.raises(ValueError,match='range'):
        SimplexRange(**arguments)


def test_growth_correction_continuous_fit_changes_real_predictions(tmp_path):
    from tft_harness.fitting import ContinuousRange, fit
    sessions, store = staged_logs(tmp_path, [[('3-2', result)] for result in
        ('win','loss','win','loss','win','loss','win','loss','win','loss')])
    report = fit(EvaluationHarness(sessions,store,repository=ROOT),
        {'opponent_growth_correction_by_stage': ContinuousRange(.5,3,start=1)},
        max_evaluations=40, bootstrap_draws=20)
    assert report.parameters['opponent_growth_correction_by_stage']['3'] == pytest.approx(2.,abs=.01)
    assert report.training_objective['candidate'] < report.training_objective['reference']


def test_probability_maps_have_identifiable_simplex_coordinates(tmp_path):
    from tft_harness.fitting import SimplexRange, fit
    sessions, store = staged_logs(tmp_path, [[('3-2',result)] for result in ('win','loss','win','loss','win')])
    report = fit(EvaluationHarness(sessions,store,repository=ROOT), {
        'emblem_count_prior': SimplexRange(2,keys=('0','1')),
        'size_level_prior': {'1': SimplexRange(2,keys=('1','2'))},
    }, max_evaluations=6,bootstrap_draws=20)
    assert sum(report.parameters['emblem_count_prior'].values()) == pytest.approx(1)
    assert sum(report.parameters['size_level_prior']['1'].values()) == pytest.approx(1)
    assert len(report.solver['ranges']) == 2


def test_stage_qualification_counts_all_eligible_fights_for_damage_objective(tmp_path):
    from tft_harness.fitting import ContinuousRange, fit
    sessions, store = staged_logs(tmp_path, [[('3-2','win'),('3-3','loss')] for _ in range(5)])
    report = fit(EvaluationHarness(sessions,store,repository=ROOT),
        {'survivor_scale_by_stage':ContinuousRange(.1,2)},metric='damage_mae',
        max_evaluations=8,stage_split_min_fights=6,bootstrap_draws=20)
    assert report.solver['stages']['3']['fights'] == 8


def test_search_rejects_unbounded_software_budgets_and_too_many_coordinates(tmp_path):
    from tft_harness.fitting import ContinuousRange, SimplexRange, fit, model_uncertainty
    sessions, store = staged_logs(tmp_path, [[('3-2','win')],[('3-2','loss')]])
    harness = EvaluationHarness(sessions,store,repository=ROOT)
    for run in (fit,model_uncertainty):
        with pytest.raises(ValueError,match='budget'):
            run(harness,{'fight_scale':ContinuousRange(.1,2)},max_evaluations=257)
    with pytest.raises(ValueError,match='128 coordinates'):
        fit(harness,{'emblem_count_prior':{str(i):ContinuousRange(.1,1) for i in range(129)}})
    with pytest.raises(ValueError,match='categories'):
        SimplexRange(130)
