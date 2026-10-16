"""Public family-2 margins use declared uncertainty in the guard's own units."""
import pytest
from dataclasses import replace

from tft_data import DataError, TaggedValue


def test_margin_combines_paired_monte_carlo_error_and_model_gap_spread():
    from tft_harness.margins import MarginInput, estimate_margin

    inputs = MarginInput('line_margin', '3', 'line', 'placement',
        TaggedValue(.1, 'default', 'Declared starting floor', '2'), False,
        (0, 2), (-3, 3), 'Paired Engine seed tape', 'Family-1 parameter bootstrap')
    result = estimate_margin(inputs)
    # The paired difference's SE is 1; model-gap sample variance is 18.
    assert result.value == pytest.approx(4.358898943540674)
    assert result.mc_standard_error == pytest.approx(1)
    assert result.model_standard_deviation == pytest.approx(4.242640687119285)
    assert result.z == 1 and result.reason is None
    assert (result.target, result.stage, result.kind, result.units) == ('line_margin', '3', 'line', 'placement')


def test_sticky_margin_doubles_uncertainty_but_never_lowers_sourced_floor():
    from tft_harness.margins import MarginInput, estimate_margin

    inputs = MarginInput('pivot_margin_by_stage', '4', 'pivot', 'placement',
        TaggedValue(10, 'owner', 'Reviewed existing stage floor', '2'), True,
        (0, 2), (-3, 3), 'Shared tape', 'Family-1 bootstrap')
    result = estimate_margin(inputs)
    assert result.value == 10 and result.z == 2


def test_missing_model_uncertainty_retains_floor_without_fabricating_sigma():
    from tft_harness.margins import MarginInput, estimate_margin

    inputs = MarginInput('transition_tolerance', '3', 'transition', 'power',
        TaggedValue(2, 'owner', 'Reviewed power floor', '2'), False,
        (0, 4), None, 'Shared power tape', '')
    result = estimate_margin(inputs)
    assert result.value == 2
    assert result.reason == 'model_gap_uncertainty_unavailable'
    assert result.model_standard_deviation is None


@pytest.mark.parametrize('rollouts,models,reason', [
    (None, (-3, 3), 'paired_rollout_uncertainty_unavailable'),
    ((1,), (-3, 3), 'insufficient_paired_rollouts'),
    ((0, 2), (1,), 'insufficient_model_gap_draws'),
])
def test_inadequate_declared_support_retains_floor(rollouts, models, reason):
    from tft_harness.margins import MarginInput, estimate_margin

    inputs = MarginInput('line_margin', '3', 'line', 'placement',
        TaggedValue(.1, 'default', 'Current floor', '2'), False,
        rollouts, models, 'Shared tape', 'Family-1 bootstrap')
    result = estimate_margin(inputs)
    assert result.value == .1 and result.reason == reason


@pytest.mark.parametrize('field,value', [
    ('target', 'fight_scale'), ('target', 'unknown'),
    ('stage', ''), ('kind', ''), ('units', 'win_probability'),
    ('floor', TaggedValue(.1, 'default', 'Floor', '1')),
    ('floor', TaggedValue(-1, 'default', 'Floor', '2')),
    ('floor', TaggedValue(True, 'default', 'Floor', '2')),
    ('floor', TaggedValue(.1, 'default', '', '2')),
    ('costly_or_sticky', 1),
    ('rollout_differences', (0, float('nan'))),
    ('model_gap_draws', (0, float('inf'))),
    ('model_gap_draws', (False, 1)),
    ('rollout_citation', ''), ('model_citation', ''),
])
def test_margin_rejects_invalid_targets_units_or_uncertainty_provenance(field, value):
    from tft_harness.margins import MarginInput

    inputs = MarginInput('line_margin', '3', 'line', 'placement',
        TaggedValue(.1, 'default', 'Starting floor', '2'), False,
        (0, 2), (-3, 3), 'Shared tape', 'Family-1 parameter bootstrap')
    with pytest.raises(DataError):
        replace(inputs, **{field: value})


def test_margin_freezes_declared_vectors_and_rejects_mutable_floor_provenance():
    from tft_harness.margins import MarginInput, estimate_margin

    rollouts, models = [0, 2], [-3, 3]
    inputs = MarginInput('line_margin', '3', 'line', 'placement',
        TaggedValue(.1, 'default', 'Starting floor', '2'), False,
        rollouts, models, 'Shared tape', 'Family-1 bootstrap')
    rollouts[1] = 100
    models[1] = 100
    assert estimate_margin(inputs).value == pytest.approx(4.358898943540674)
    with pytest.raises(DataError):
        replace(inputs, floor=TaggedValue(.1, 'default', {'citation': 'mutable'}, '2'))


def test_margin_never_emits_nonfinite_uncertainty():
    from tft_harness.margins import MarginInput, estimate_margin

    inputs = MarginInput('pivot_margin_by_stage', '3', 'pivot', 'placement',
        TaggedValue(.5, 'default', 'Starting floor', '2'), True,
        (0, 0), (-1e308, 1e308), 'Shared tape', 'Family-1 bootstrap')
    with pytest.raises(DataError):
        estimate_margin(inputs)


def scale_dependent_choices(context):
    """Two options on one shared rollout tape; the gap moves with family-1 fight_scale."""
    from tft_engine import Advice, ScoredOption
    scale = float(context.data.tunable('fight_scale'))
    best = [2, 4, 3, 5]
    other = [3+.5*scale, 4+.5*scale, 4, 6]
    return (Advice('augment', 'Pick A', 'act_this_phase', .9, 'fixture-model',
        decision_id=context.snapshot.snapshot_id+':augment', option_id='a',
        options=(ScoredOption('a', 'pick', {'augment_id': 'A', 'slot': 0,
                     'after': {'seed': context.seed, 'rollout_placements': best}}, sum(best)/4, 99),
                 ScoredOption('b', 'pick', {'augment_id': 'B', 'slot': 1,
                     'after': {'seed': context.seed, 'rollout_placements': other}}, sum(other)/4, 99))),)


def margin_harness(tmp_path):
    from tft_engine import DomainHook
    from tft_harness import EvaluationHarness
    from tests.test_replay_contracts import ROOT, logged_game

    sessions, store, _, _ = logged_game(tmp_path, mode='baseline')
    return EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('augment', (), advice=scale_dependent_choices),))


def test_stage_margins_combine_shared_tape_error_with_family1_draw_spread(tmp_path):
    from tft_harness.margins import paired_guards, replay_draws, stage_margins

    harness = margin_harness(tmp_path)
    guards = paired_guards(replay_draws(harness, [{}])[0], kind='augment')
    assert [(guard.stage, guard.best_option, guard.runner_up) for guard in guards] == [('3', 'a', 'b')]
    assert guards[0].differences == (1.5, .5, 1, 1)
    draws = replay_draws(harness, [{'fight_scale': value} for value in (1, 2, 3)])
    result = stage_margins(guards, [paired_guards(batches, kind='augment') for batches in draws],
        target='comp_defining_margin', floor=TaggedValue(.1, 'default', 'Starting floor', '2'),
        costly_or_sticky=True, rollout_citation='Engine shared seed tape',
        model_citation='Declared family-1 fight_scale draws 1, 2, 3')
    # Shared-tape SE: stdev(1.5,.5,1,1)/2 = .2041; draw means 1, 1.25, 1.5 have SD .25.
    assert result['3']['value'] == pytest.approx(2*((.5/3)/4+.0625)**.5)
    assert result['3']['decisions'] == 1 and result['3']['available'] == 1
    assert result['3']['z'] == 2 and result['3']['reasons'] == {}
    assert result.tunable_value() == {'3': pytest.approx(.6454972243679028)}


def test_stage_margins_keep_the_floor_when_draws_cannot_measure_model_error(tmp_path):
    from tft_harness.margins import paired_guards, replay_draws, stage_margins

    harness = margin_harness(tmp_path)
    guards = paired_guards(replay_draws(harness, [{}])[0], kind='augment')
    result = stage_margins(guards, [paired_guards(replay_draws(harness, [{'fight_scale': 2}])[0], kind='augment')],
        target='comp_defining_margin', floor=TaggedValue(.1, 'default', 'Starting floor', '2'),
        costly_or_sticky=True, rollout_citation='tape', model_citation='one draw')
    assert result['3']['value'] == .1
    assert result['3']['reasons'] == {'insufficient_model_gap_draws': 1}
    with pytest.raises(DataError, match='placement'):
        stage_margins(guards, [], target='transition_tolerance',
            floor=TaggedValue(2, 'owner', 'Power floor', '2'), costly_or_sticky=False,
            rollout_citation='tape', model_citation='draws')
    with pytest.raises(ValueError, match='family 1'):
        replay_draws(harness, [{'line_margin': 1}])
