"""Family-3 priors come from public statistics by empirical Bayes behind a board gate."""
from dataclasses import replace
from math import log

import pytest

from tft_data import Entity, Statistic, TaggedValue
from tests.test_replay_contracts import historical_data


def unit_row(entity, stars, rate, samples, patch='fixture', **extra):
    return Statistic(entity, 'unit', 4.5, samples, patch, 'tactics.tools', unit_star=stars,
        top4_rate=rate, **extra)


def trait_row(entity, breakpoint, rate, samples, patch='fixture'):
    return Statistic(entity, 'trait', 4.5, samples, patch, 'tactics.tools', breakpoint=breakpoint,
        top4_rate=rate)


def public_data(tmp_path, statistics, *, extra_entities=()):
    _, data = historical_data(tmp_path)
    entities = dict(data.entities)
    for index, cost in enumerate((1, 1, 2, 2, 3, 3)):
        identity = f'u{index}'
        entities[identity] = Entity(identity, 'unit', identity, cost,
            values={'item_class': TaggedValue('carry', 'owner')})
    for identity in ('ember', 'tide'):
        entities[identity] = Entity(identity, 'trait', identity, values={'breakpoints': TaggedValue([2], 'owner')})
    for identity in ('sword', 'staff'):
        entities[identity] = Entity(identity, 'item', identity, values={'item_class': TaggedValue('ad', 'owner')})
    for entity in extra_entities:
        entities[entity.id] = entity
    tunables = dict(data.tunables) | {'item_class_prior': TaggedValue({'carry': {'ad': .1, 'ap': .2}},
        'owner', '', '3')}
    return replace(data, entities=entities, statistics=tuple(statistics), tunables=tunables)


def test_priors_wait_for_about_five_hundred_boards_and_keep_old_priors(tmp_path):
    from tft_harness.priors import fit_priors

    data = public_data(tmp_path, [unit_row('u0', 1, .6, 499), unit_row('u1', 1, .4, 400),
        unit_row('u2', 2, .6, 900, patch='previous')])
    result = fit_priors(data)
    assert result.status == 'insufficient_boards'
    assert result.boards == 499 and result.min_boards == 500
    assert result.fields == {}


def test_cost_star_baseline_pools_current_patch_rates_on_the_lobby_logit_scale(tmp_path):
    from tft_harness.priors import fit_priors

    data = public_data(tmp_path, [unit_row('u0', 1, .6, 600), unit_row('u1', 1, .4, 400),
        unit_row('u4', 2, .7, 900, stale=True)])
    result = fit_priors(data)
    assert result.status == 'candidate'
    baseline = result.fields['cost_star_baseline']
    # Pooled top-4 rate (360+160)/1000 = .52 against the .5 lobby rate.
    assert baseline['1']['1'] == pytest.approx(log(.52/.48))
    # Cells without current-patch, non-stale evidence keep the committed value.
    assert baseline['3']['2'] == 4
    assert result.diagnostics['cost_star_baseline']['cells'] == {'1/1': 1000}


def test_unit_prior_strength_is_smaller_when_public_rates_are_more_dispersed(tmp_path):
    from tft_harness.priors import fit_priors

    def strength(spread):
        rows = [unit_row(f'u{index}', 1, .5 + (spread if index % 3 else -spread), 2000)
            for index in range(6)]
        (tmp_path/str(spread)).mkdir()
        result = fit_priors(public_data(tmp_path/str(spread), rows))
        return result.fields['unit_prior_strength']

    narrow, wide = strength(.03), strength(.12)
    assert 0 < wide < narrow


def test_rates_with_no_overdispersion_carry_the_committed_prior_strength(tmp_path):
    from tft_harness.priors import fit_priors

    rows = [trait_row('ember', 2, .5, 1000), trait_row('tide', 2, .5, 3000)]
    result = fit_priors(public_data(tmp_path, rows))
    assert 'trait_prior_strength' not in result.fields
    assert result.carried['trait_prior_strength'] == 'no_overdispersion_prior_unbounded'


def test_item_priors_use_normal_empirical_bayes_on_placement_deltas(tmp_path):
    from tft_harness.priors import fit_priors

    base = Statistic('u0', 'unit', 4.5, 9000, 'fixture', 'metatft')
    rows = [base] + [Statistic('u0', 'unit', 4.5-delta, 1000, 'fixture', 'metatft', item_id=item, variance=5.0)
        for delta, item in ((.2, 'sword'), (.4, 'staff'), (.6, 'blade'))]
    blade = Entity('blade', 'item', 'blade', values={'item_class': TaggedValue('ad', 'owner')})
    result = fit_priors(public_data(tmp_path, rows, extra_entities=(blade,)))
    # Class mean .4; residual second moment .08/3 less noise 5/1000 is tau^2.
    assert result.fields['item_class_prior']['carry']['ad'] == pytest.approx(.4)
    assert result.fields['item_class_prior']['carry']['ap'] == .2
    assert result.fields['item_prior_strength'] == pytest.approx(5/(.08/3-.005))


def test_augment_priors_stay_carried_with_explicit_reasons(tmp_path):
    from tft_harness.priors import fit_priors

    result = fit_priors(public_data(tmp_path, [unit_row('u0', 1, .6, 600), unit_row('u1', 1, .4, 400)]))
    assert result.carried['augment_prior_strength'] == 'augment_statistics_unavailable'
    assert result.carried['augment_flag_prior_multiplier'] == 'cross_patch_holdout_unavailable'
    assert set(result.fields) | set(result.carried) == {'cost_star_baseline', 'unit_prior_strength',
        'trait_prior_strength', 'item_class_prior', 'item_prior_strength', 'augment_prior_strength',
        'augment_flag_prior_multiplier'}
