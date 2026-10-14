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
