"""Only qualified public sufficient statistics may fit family-3 priors."""
from dataclasses import replace
from math import log
import pytest
from tft_data import Entity, Statistic, TaggedValue
from tests.test_replay_contracts import historical_data


def public_data(tmp_path):
    _, data = historical_data(tmp_path)
    entities = dict(data.entities)
    for i in range(6):
        entities[f'u{i}'] = Entity(f'u{i}', 'unit', f'Unit {i}', 1,
            values={'item_class': TaggedValue('carry', 'owner')})
    for i in range(3):
        for kind, prefix in (('item','i'), ('augment','a'), ('trait','t')):
            entities[f'{prefix}{i}'] = Entity(f'{prefix}{i}', kind, f'{kind} {i}',
                values={'item_class': TaggedValue('ad', 'owner')} if kind == 'item' else {})
    tunables = dict(data.tunables)
    for name, value in (('item_class_prior', {'carry': {'ad': .1, 'ap': .2}}),
            ('augment_prior_strength',100), ('augment_flag_prior_multiplier',2)):
        tunables[name] = TaggedValue(value, 'owner', '', '3')
    return replace(data, entities=entities, tunables=tunables)


def cohort(rows, *, patch='fixture', identity='current', day=1, boards=10000):
    return {'id': identity, 'patch': patch, 'source': 'tactics.tools',
        'citation': 'https://tactics.tools/public-fixture',
        'updated_at': f'2026-10-{day+1:02}T12:00:00+00:00',
        'start': f'2026-10-{day:02}T00:00:00+00:00', 'end': f'2026-10-{day+1:02}T00:00:00+00:00',
        'distinct_boards': boards,
        'qualification': {'public_aggregate': True, 'distinct_boards': True, 'independent_rows': True},
        'rows': rows}


def evidence(*cohorts):
    return {'schema': 'public_prior_cohorts_v1', 'cohorts': list(cohorts)}


def binomial(kind, entity, successes, trials=1000):
    return {'kind': kind, 'entity_id': entity, 'successes': successes, 'trials': trials,
        **({'unit_star': 1} if kind == 'unit' else {'breakpoint': 2})}


def normal(kind, entity, mean, **extra):
    return {'kind': kind, 'entity_id': entity, 'mean': mean, 'variance': 5., 'trials': 1000, **extra}


def test_default_carries_and_never_infers_boards_from_entity_count(tmp_path):
    from tft_harness.priors import FAMILY_3, fit_priors
    data = replace(public_data(tmp_path), statistics=(Statistic('u0', 'unit', 4.5, 90000,
        'fixture', 'tactics.tools', unit_star=1, top4_rate=.543),))
    result = fit_priors(data)
    assert result.fields == {} and result.boards == 0
    assert set(result.carried) == set(FAMILY_3)
    assert result.status == 'unqualified_public_evidence'


def test_gate_uses_explicit_distinct_board_count(tmp_path):
    from tft_harness.priors import fit_priors
    result = fit_priors(public_data(tmp_path), evidence=evidence(cohort([binomial('unit','u0',240,400)],boards=499)))
    assert result.fields == {} and result.boards == 499 and result.status == 'insufficient_boards'


def test_exact_binomial_baseline_preserves_missing_cells(tmp_path):
    from tft_harness.priors import fit_priors
    result = fit_priors(public_data(tmp_path), evidence=evidence(cohort([
        binomial('unit','u0',360,600), binomial('unit','u1',160,400)])))
    assert result.fields['cost_star_baseline']['1']['1'] == pytest.approx(log(.52/.48))
    assert result.fields['cost_star_baseline']['3']['2'] == 4
    assert result.diagnostics['cohort']['distinct_boards'] == 10000


@pytest.mark.parametrize('change', [
    {'qualification': {}}, {'citation': ''}, {'source': 'owner'},
    {'updated_at': '2026-09-01T00:00:00+00:00'}, {'distinct_boards': True},
    {'start':'2026-10-03T00:00:00+00:00'},
])
def test_invalid_cohort_rejected(tmp_path, change):
    from tft_harness.priors import fit_priors
    with pytest.raises(ValueError):
        fit_priors(public_data(tmp_path), evidence=evidence(cohort([])|change))


@pytest.mark.parametrize('count', [543.2, True, 1001, -1])
def test_rounded_rates_cannot_be_exact_success_counts(tmp_path, count):
    from tft_harness.priors import fit_priors
    with pytest.raises(ValueError):
        fit_priors(public_data(tmp_path), evidence=evidence(cohort([binomial('unit','u0',count)])))


def test_beta_binomial_strength_decreases_with_dispersion(tmp_path):
    from tft_harness.priors import fit_priors
    data = public_data(tmp_path)
    def fit(spread):
        rows = [binomial('unit',f'u{i}',500+(spread if i%2 else -spread)) for i in range(6)]
        rows += [binomial('trait',f't{i}',500+(spread if i%2 else -spread)) for i in range(3)]
        return fit_priors(data,evidence=evidence(cohort(rows))).fields
    narrow, wide = fit(30), fit(120)
    for name in ('unit_prior_strength','trait_prior_strength'):
        assert 0 < wide[name] < narrow[name]


def test_item_and_augment_normal_empirical_bayes(tmp_path):
    from tft_harness.priors import fit_priors
    rows = [normal('item','u0',delta,item_id=f'i{i}') for i,delta in enumerate((.2,.4,.6))]
    rows += [normal('augment',f'a{i}',delta,prior_mean=0.) for i,delta in enumerate((-.2,0.,.2))]
    fields = fit_priors(public_data(tmp_path),evidence=evidence(cohort(rows))).fields
    assert fields['item_class_prior']['carry']['ad'] == pytest.approx(.4)
    assert fields['item_class_prior']['carry']['ap'] == .2
    for name in ('item_prior_strength','augment_prior_strength'):
        assert fields[name] == pytest.approx(5/(.08/3-.005))


def temporal():
    return [cohort([normal('augment',f'a{i}',.05 if late else .8,prior_mean=0.,flagged=True)
        for i in range(3)], patch=patch, identity=patch+str(late),day=1+index*4+int(late))
        for index,patch in enumerate(('previous','fixture')) for late in (False,True)]


def test_flag_multiplier_uses_distinct_patches_and_unseen_holdout(tmp_path):
    from tft_harness.priors import fit_priors
    result = fit_priors(public_data(tmp_path),evidence=evidence(*temporal()))
    assert result.fields['augment_flag_prior_multiplier'] > 2
    diagnostics = result.diagnostics['augment_flag_prior_multiplier']
    assert diagnostics['training_patches'] == ['previous'] and diagnostics['holdout_patch'] == 'fixture'
    assert diagnostics['candidate_loss'] <= diagnostics['reference_loss']


def test_temporal_same_patch_unavailable_and_overlap_rejected(tmp_path):
    from tft_harness.priors import fit_priors
    data = public_data(tmp_path)
    result = fit_priors(data,evidence=evidence(*temporal()[-2:]))
    assert result.carried['augment_flag_prior_multiplier'] == 'cross_patch_holdout_unavailable'
    cohorts = temporal()
    cohorts[1]['start'] = cohorts[0]['start']
    with pytest.raises(ValueError, match='overlap'):
        fit_priors(data,evidence=evidence(*cohorts))


def test_old_patch_cannot_unlock_gate(tmp_path):
    from tft_harness.priors import FAMILY_3, fit_priors
    result = fit_priors(public_data(tmp_path),evidence=evidence(cohort([],patch='previous')))
    assert result.fields == {} and result.boards == 0
    assert set(result.carried) == set(FAMILY_3)


def test_missing_variance_is_rejected_without_lobby_noise_fallback(tmp_path):
    from tft_harness.priors import fit_priors
    row = normal('item','u0',.2,item_id='i0')
    row.pop('variance')
    with pytest.raises(ValueError,match='variance'):
        fit_priors(public_data(tmp_path),evidence=evidence(cohort([row])))


def test_independent_row_trials_cannot_exceed_certified_boards(tmp_path):
    from tft_harness.priors import fit_priors
    with pytest.raises(ValueError,match='population'):
        fit_priors(public_data(tmp_path),evidence=evidence(cohort([
            binomial('unit','u0',500),binomial('unit','u1',500)],boards=1000)))


def test_no_overdispersion_retains_prior_and_partition_is_complete(tmp_path):
    from tft_harness.priors import FAMILY_3, fit_priors
    rows = [binomial('trait',f't{i}',500) for i in range(3)]
    result = fit_priors(public_data(tmp_path),evidence=evidence(cohort(rows)))
    assert result.carried['trait_prior_strength'] == 'no_overdispersion_prior_unbounded'
    assert set(result.fields).isdisjoint(result.carried)
    assert set(result.fields)|set(result.carried) == set(FAMILY_3)


def test_late_patch_regression_does_not_publish_flag_multiplier(tmp_path):
    from tft_harness.priors import fit_priors
    cohorts = temporal()
    for row in cohorts[-1]['rows']:
        row['mean'] = .8
    result = fit_priors(public_data(tmp_path),evidence=evidence(*cohorts))
    assert 'augment_flag_prior_multiplier' not in result.fields
    assert result.carried['augment_flag_prior_multiplier'] == 'temporal_holdout_regression'


def test_partial_table_fit_lists_public_and_carried_cells(tmp_path):
    from tft_harness.priors import fit_priors
    data = public_data(tmp_path)
    result = fit_priors(data, evidence=evidence(cohort([
        binomial('unit', 'u0', 600), normal('item', 'u0', .4, item_id='i0')])))
    cells = result.diagnostics['table_cells']
    assert cells['cost_star_baseline']['fitted_cells'] == [['1', '1']]
    assert ['3', '2'] in cells['cost_star_baseline']['carried_cells']
    assert cells['item_class_prior']['fitted_cells'] == [['carry', 'ad']]
    assert cells['item_class_prior']['carried_cells'] == [['carry', 'ap']]
    assert cells['item_class_prior']['carried_source'] == 'owner'
    assert cells['item_class_prior']['carried_citation'] == data.tunables['item_class_prior'].citation


def test_removed_historical_augment_does_not_invalidate_temporal_holdout(tmp_path):
    from tft_harness.priors import fit_priors
    cohorts = temporal()
    for old in cohorts[:2]:
        for row in old['rows']:
            row['entity_id'] = 'removed-' + row['entity_id']
    data = public_data(tmp_path)
    result = fit_priors(data, evidence=evidence(*cohorts))
    assert result.fields['augment_flag_prior_multiplier'] > 2
    assert result.diagnostics['augment_flag_prior_multiplier']['training_patches'] == ['previous']
    cohorts[-1]['rows'][0]['entity_id'] = 'removed-current'
    with pytest.raises(ValueError, match='known matching entity'):
        fit_priors(data, evidence=evidence(*cohorts))
