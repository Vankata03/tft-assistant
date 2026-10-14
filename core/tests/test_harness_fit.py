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
