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


def test_default_engine_produces_real_paired_econ_rollouts(tmp_path):
    import tomllib
    import tomli_w
    from tests.test_replay_contracts import historical_data, log_snapshot, NOW, ROOT
    from tft_core.storage import SessionStore
    from tft_harness import EvaluationHarness
    from tft_harness.margins import paired_guards, replay_draws
    store, data = historical_data(tmp_path)
    path = tmp_path/'patch/tunables.toml'
    document = tomllib.loads(path.read_text())
    document['fields']['line_candidate_cap']['value'] = 4
    path.write_text(tomli_w.dumps(document))
    data = store.refresh(path.parent, now=NOW).snapshot
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config')
    sessions.start_game('901', set_id='18', patch=data.patch, data_snapshot_id=data.snapshot_id,
        timestamp=NOW.isoformat())
    sessions.append_event('snapshot', log_snapshot(data), timestamp=NOW.isoformat())
    sessions.end_game(timestamp=NOW.isoformat())
    harness = EvaluationHarness(sessions, store, repository=ROOT)
    guards = paired_guards(replay_draws(harness, [{}])[0], kind='econ')
    assert guards and all(len(guard.differences) >= 2 for guard in guards)


def test_margin_fit_produces_values_from_real_engine_tapes_and_training_refits(tmp_path):
    from tests.test_harness_fit import staged_logs
    from tests.test_replay_contracts import ROOT
    from tft_harness import EvaluationHarness
    from tft_harness.overlay import TunableOverlay
    from tft_harness.margins import fit_margins
    sessions, store = staged_logs(tmp_path, [[('3-2', result)] for result in
        ('win','loss','win','win','loss')])
    accepted = TunableOverlay(store, {'line_candidate_cap': 4}, tagged_fields={
        'line_margin': TaggedValue(.1, 'default', 'Declared fixture starting floor', '2')})
    result = fit_margins(EvaluationHarness(sessions, accepted, repository=ROOT),
        {'fight_scale': [.25,1,2]}, draws=3, seed=17)
    assert result['model']['method'] == 'training-game bootstrap refits'
    assert result['fields']['line_margin']['3'] >= .1
    assert result['diagnostics']['line_margin']['3']['available'] > 0
    assert result['carried']['transition_tolerance'] == 'compatible_paired_guard_unavailable'
    assert 'game_id' not in str(result)


def test_missing_model_sample_carries_all_margins_without_blocking_family1(tmp_path):
    from tests.test_harness import combat_logs
    from tests.test_replay_contracts import ROOT
    from tft_harness import EvaluationHarness
    from tft_harness.margins import fit_margins
    sessions, store = combat_logs(tmp_path, results=('win','loss'))
    result = fit_margins(EvaluationHarness(sessions, store, repository=ROOT),
        {'fight_scale': [.25,1,2]}, draws=3)
    assert result['fields'] == {}
    assert set(result['carried'].values()) == {'insufficient_training_games_for_model_uncertainty'}


def rival_store(tmp_path):
    """Fixture data with a second Guide on the same unit; its Line rolls later."""
    from datetime import timedelta
    from tests.test_replay_contracts import GuideFeed, NOW, historical_data

    class RivalFeed(GuideFeed):
        name = 'rival-fixture'

        def fetch(self):
            guide = super().fetch()['guides'][0]
            return {'guides': [guide | {'id': 'rival', 'line': [{'round': '4-2', 'level': 1}]}]}

    store, _ = historical_data(tmp_path)
    data = store.refresh(tmp_path/'patch', now=NOW+timedelta(seconds=1), sources=(RivalFeed(),)).snapshot
    assert sorted(data.guides) == ['guide', 'rival']
    return store, data


def log_rounds(sessions, data, game_id, rounds, *, at=None, **fields):
    """One finished game with a planning snapshot per (round_id, extra fields)."""
    from datetime import timedelta
    from tests.test_replay_contracts import NOW, log_snapshot
    at = at or NOW
    sessions.start_game(game_id, set_id='18', patch=data.patch, data_snapshot_id=data.snapshot_id,
        timestamp=at.isoformat())
    for index, (round_id, extra) in enumerate(rounds):
        moment = at+timedelta(seconds=10*index)
        snapshot = log_snapshot(data, at=moment, snapshot_id=f'{game_id}-{index}', **(fields | extra))
        sessions.append_event('snapshot', snapshot | {'round_id': round_id, 'game_id': game_id},
            timestamp=moment.isoformat())
    sessions.end_game(placement=4, timestamp=(at+timedelta(seconds=10*len(rounds)+5)).isoformat())


def scaled_rival(weight, *, when_field=None):
    """A domain fit term on the rival comp that moves with family-1 fight_scale."""
    from tft_engine import DomainHook, FitTerm
    return DomainHook('augment', (), fit=lambda comp, context: FitTerm(
        weight*float(context.data.tunable('fight_scale'))
        if comp == 'rival' and (when_field is None or context.snapshot.field(when_field)) else 0, 'fixture'))


def plan_harness(tmp_path, rounds, hook, **fields):
    from tests.test_replay_contracts import ROOT
    from tft_core.storage import SessionStore
    from tft_engine import Board, Unit
    from tft_harness import EvaluationHarness
    from tft_harness.overlay import TunableOverlay
    store, data = rival_store(tmp_path)
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config')
    log_rounds(sessions, data, '901', rounds, **({'board': Board((Unit('unit', stars=2),))} | fields))
    # Simulate both comps so the Engine compares two same-seed tapes.
    overlay = TunableOverlay(store, {'challengers_simulated': 2, 'open_candidate_count': 2})
    return EvaluationHarness(sessions, overlay, repository=ROOT, hooks=(hook,))


SCALES = [{'fight_scale': value} for value in (1, 2, 3)]


def test_pivot_guards_pair_the_committed_target_with_its_challenger_and_split_reraises(tmp_path):
    from tft_harness.margins import plan_guards, replay_draws, reraise_extra, stage_margins

    buff = {'augments': ['buff']}
    harness = plan_harness(tmp_path, [('2-2', {}), ('2-3', buff), ('2-4', buff), ('2-5', buff)],
        scaled_rival(-4, when_field='augments'))
    batches = replay_draws(harness, [{}])[0]
    pivots = plan_guards(batches, kind='pivot')
    # 2-2 compares equal comps; 2-3 calls the pivot; 2-4 adopts the player's comp (no check).
    assert [(guard.stage, guard.best_option, guard.runner_up, guard.differences) for guard in pivots] == [
        ('2', 'guide', 'rival', (0.0,)*4), ('2', 'guide', 'rival', (4.0,)*4)]
    reraises = plan_guards(batches, kind='pivot_reraise')
    assert [(guard.stage, guard.base_key, guard.differences) for guard in reraises] == [('2', '2', (4.0,)*4)]
    draws = replay_draws(harness, SCALES)
    floor = TaggedValue(.5, 'default', 'Declared pivot floor', '2')
    base = stage_margins(pivots, [plan_guards(batch, kind='pivot') for batch in draws],
        target='pivot_margin_by_stage', floor=floor, costly_or_sticky=True,
        rollout_citation='tape', model_citation='fight_scale draws')
    # Gaps 0 and 4s over s=1,2,3: model SDs 0 and 4, z=2, root mean square sqrt((0+64)/2).
    assert base['2']['value'] == pytest.approx(32**.5) and base['2']['z'] == 2
    extra = reraise_extra(reraises, [plan_guards(batch, kind='pivot_reraise') for batch in draws],
        floor=TaggedValue(.2, 'default', 'Declared extra floor', '2'),
        pivot_table={'default': .5, 'post_roll_down': .8}, rollout_citation='tape', model_citation='draws')
    # The re-raise needs 2 * 4 = 8 placements; stage 2 already applies the .5 default.
    assert extra['2']['value'] == pytest.approx(7.5)
    assert extra['2']['reraise_margin'] == pytest.approx(8)


def test_comp_defining_guard_reads_the_open_plan_lead_not_augment_options(tmp_path):
    from tft_engine import Board, Unit
    from tft_harness.margins import paired_guards, plan_guards, replay_draws, stage_margins

    # A one-star carry before 3-2 leaves the plan Open, so only the augment-defined lead can commit.
    harness = plan_harness(tmp_path, [('2-1', {})], scaled_rival(-.5), board=Board((Unit('unit'),)))
    batches = replay_draws(harness, [{}])[0]
    guards = plan_guards(batches, kind='comp_defining')
    assert [(guard.stage, guard.best_option, guard.runner_up, guard.differences) for guard in guards] == [
        ('2', 'guide', 'rival', (.5,)*4)]
    # No augment option comparison exists to be relabelled.
    assert paired_guards(batches, kind='augment') == ()
    result = stage_margins(guards, [plan_guards(batch, kind='comp_defining') for batch in replay_draws(harness, SCALES)],
        target='comp_defining_margin', floor=TaggedValue(.3, 'default', 'Declared floor', '2'),
        costly_or_sticky=True, rollout_citation='tape', model_citation='draws')
    # Leads .5s over s=1,2,3 have SD .5; z=2.
    assert result['2']['value'] == pytest.approx(1)


def test_transition_tolerance_uses_exact_power_gaps_and_family1_power_draws(tmp_path):
    from tests.test_replay_contracts import ROOT, historical_data
    from tft_core.storage import SessionStore
    from tft_engine import Board, Unit
    from tft_harness import EvaluationHarness
    from tft_harness.margins import replay_draws, stage_margins, transition_guards

    store, data = historical_data(tmp_path)
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config')
    log_rounds(sessions, data, '901', [('3-2', {})], board=Board((Unit('unit', position=0),)),
        bench=[Unit('unit', stars=2)])
    from tft_harness.overlay import TunableOverlay
    harness = EvaluationHarness(sessions, TunableOverlay(store, {'capacity_transition_state_cap': 1000}),
        repository=ROOT)
    guards = transition_guards(replay_draws(harness, [{}])[0])
    assert len(guards) == 1 and guards[0].units == 'power' and guards[0].deterministic
    gap = guards[0].value
    assert gap < 0  # the bench 2-star is stronger than the kept 1-star
    draws = replay_draws(harness, [{'unit_weight': value} for value in (1, 2, 3)])
    result = stage_margins(guards, [transition_guards(batch) for batch in draws],
        target='transition_tolerance', floor=TaggedValue(.01, 'default', 'Declared floor', '2'),
        costly_or_sticky=False, rollout_citation='exact power', model_citation='unit_weight draws')
    # Power is linear in unit_weight, so gaps g, 2g, 3g have SD |g|; no Monte Carlo term.
    assert result['3']['value'] == pytest.approx(abs(gap))
    assert result['3']['units'] == 'power' and result['3']['reasons'] == {}


def shop_and_threat_advice(context):
    """Built-in shop and positioning payload shapes whose values move with family-1 tunables."""
    from tft_engine import Advice, ScoredOption
    weight = float(context.data.tunable('unit_weight'))
    half_life = float(context.data.tunable('sighting_half_life_rounds'))
    shop = Advice('shop', 'Hold shop', 'information', .5, 'analytic_shop', decision_id='shop', option_id='shop',
        options=(ScoredOption('shop:0:a', 'buy', {'slot': 0, 'unit_id': 'a', 'eligible_reason': None,
                     'power_gain': .1*weight}, reason='no_improvement'),
                 ScoredOption('shop:1:b', 'buy', {'slot': 1, 'unit_id': 'b', 'eligible_reason': 'target_key',
                     'power_gain': 5*weight}, reason='target_key'),
                 ScoredOption('shop:hold', 'hold', {'operation': 'hold'}, reason='analytic_unchanged_baseline')))
    layout = Advice('positioning', 'Move to target layout', 'act_this_phase', .5, 'template_layout',
        option_id='positioning:layout', payload={'operation': 'layout', 'threats_available': True,
            'threat_shares': {'aoe': .2*half_life, 'backline_access': .5}})
    return (shop, layout)


def test_shop_power_and_threat_share_margins_use_their_own_units(tmp_path):
    from tft_engine import DomainHook
    from tft_harness.margins import (pooled, replay_draws, share_band, share_guards, shop_guards,
        stage_margins)
    from tests.test_replay_contracts import ROOT, logged_game
    from tft_harness import EvaluationHarness

    sessions, store, _, _ = logged_game(tmp_path, mode='baseline')
    harness = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('fixture', (), advice=shop_and_threat_advice),))
    batches = replay_draws(harness, [{}])[0]
    shops = shop_guards(batches)
    # Target-key units are bought before the power threshold applies.
    assert [(guard.best_option, guard.value, guard.units) for guard in shops] == [('shop:0:a', pytest.approx(.1), 'power')]
    draws = [{'unit_weight': value, 'sighting_half_life_rounds': value} for value in (1, 2, 3)]
    replayed = replay_draws(harness, draws)
    result = stage_margins(shops, [shop_guards(batch) for batch in replayed], target='board_power_buy_min',
        floor=TaggedValue(.05, 'default', 'Declared floor', '2'), costly_or_sticky=False,
        rollout_citation='exact power', model_citation='draws')
    assert result['3']['value'] == pytest.approx(.1)
    shares = pooled(share_guards(batches))
    assert sorted((guard.best_option, guard.value) for guard in shares) == [('aoe', pytest.approx(.2)), ('backline_access', .5)]
    row = stage_margins(shares, [pooled(share_guards(batch)) for batch in replayed], target='threat_share_on',
        floor=TaggedValue(0, 'default', 'Zero floor', '2'), costly_or_sticky=False,
        rollout_citation='exact share', model_citation='draws')['all']
    # aoe shares .2, .4, .6 have SD .2; the fixed share has none: RMS sqrt(.04/2).
    assert row['unfloored'] == pytest.approx(.02**.5)
    on, off = share_band(row, on_floor=TaggedValue(.5, 'default', 'on', '2'), off_floor=TaggedValue(.3, 'default', 'off', '2'))
    assert (on, off) == (pytest.approx(.4+.02**.5), pytest.approx(.4-.02**.5))
    # Small share noise keeps the sourced band.
    assert share_band(row | {'unfloored': .01}, on_floor=TaggedValue(.5, 'default', 'on', '2'),
        off_floor=TaggedValue(.3, 'default', 'off', '2')) == (pytest.approx(.5), pytest.approx(.3))
    with pytest.raises(DataError):
        stage_margins(shares, [], target='board_power_buy_min', floor=TaggedValue(.05, 'default', 'f', '2'),
            costly_or_sticky=False, rollout_citation='x', model_citation='y')


def test_review_min_cost_combines_paired_choice_tapes_with_model_spread(tmp_path):
    from datetime import timedelta
    from tests.test_replay_contracts import NOW, ROOT, logged_game
    from tft_engine import DomainHook
    from tft_harness import EvaluationHarness
    from tft_harness.overlay import TunableOverlay
    from tft_harness.margins import pooled, replay_draws, review_guards, stage_margins

    sessions, store, _, _ = logged_game(tmp_path, finish=False, mode='baseline')
    sessions.append_event('augment_pick', {'slot': 1, 'augment_id': 'B', 'choice_token': 'offer',
        'evidence': 'positive_pick_confirmation'}, timestamp=(NOW+timedelta(seconds=1)).isoformat())
    sessions.end_game(timestamp=(NOW+timedelta(seconds=2)).isoformat())
    harness = EvaluationHarness(sessions, store, repository=ROOT,
        hooks=(DomainHook('augment', (), advice=scale_dependent_choices),))
    guards = pooled(review_guards(replay_draws(harness, [{}])[0], store))
    # The player's B against the Engine's A on the same tape.
    assert [(guard.kind, guard.best_option, guard.runner_up, guard.differences) for guard in guards] == [
        ('review:augment', 'a', 'b', (1.5, .5, 1, 1))]
    draws = replay_draws(harness, SCALES)
    model = [pooled(review_guards(batch, TunableOverlay(store, draw))) for batch, draw in zip(draws, SCALES)]
    result = stage_margins(guards, model, target='review_min_cost',
        floor=TaggedValue(.05, 'default', 'Declared floor', '2'), costly_or_sticky=False,
        rollout_citation='paired choices', model_citation='draws')
    # Shared-tape SE .2041 and draw-mean SD .25, z=1.
    assert result['all']['value'] == pytest.approx(((.5/3)/4+.0625)**.5)


def test_margin_fit_produces_plan_power_and_share_targets_from_replayed_training_games(tmp_path):
    from datetime import timedelta
    import tomllib
    import tomli_w
    from tests.test_replay_contracts import NOW, ROOT, log_snapshot
    from tft_core.storage import SessionStore
    from tft_engine import Board, DomainHook, Unit
    from tft_harness import EvaluationHarness
    from tft_harness.overlay import TunableOverlay
    from tft_harness.margins import fit_margins

    store, _ = rival_store(tmp_path)
    path = tmp_path/'patch'/'static.toml'
    static = tomllib.loads(path.read_text())
    static['fields']['round_types']['value']['3-2'] = 'combat'
    path.write_text(tomli_w.dumps(static))
    data = store.refresh(path.parent, now=NOW+timedelta(seconds=2)).snapshot
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config', live_installed=True)
    sessions.set_mode('silent')
    for index, result in enumerate(('win', 'loss', 'win', 'win', 'loss')):
        game_id, at = str(901+index), NOW+timedelta(days=index)
        sessions.start_game(game_id, set_id='18', patch=data.patch, data_snapshot_id=data.snapshot_id,
            timestamp=at.isoformat())
        sessions.append_event('snapshot', log_snapshot(data, at=at, snapshot_id=f'{game_id}-0',
            board=Board((Unit('unit', stars=2),))) | {'game_id': game_id}, timestamp=at.isoformat())
        sessions.append_event('fight_start', {'round_id': '3-2', 'opponent_id': 'rival', 'hp_before': 73},
            timestamp=(at+timedelta(seconds=1)).isoformat())
        sessions.append_event('fight_result', {'round_id': '3-2', 'opponent_id': 'rival', 'hp_before': 73,
            'hp_after': 73 if result == 'win' else 68, 'hp_lost': 0 if result == 'win' else 5, 'result': result},
            timestamp=(at+timedelta(seconds=10)).isoformat())
        sessions.end_game(placement=4, timestamp=(at+timedelta(hours=1)).isoformat())
    floors = {name: TaggedValue(value, 'default', 'Declared fixture starting floor', '2') for name, value in {
        'pivot_margin_by_stage': {'default': .5, 'post_roll_down': .8}, 'board_power_buy_min': .05,
        'threat_share_on': .5, 'threat_share_off': .3, 'line_margin': .1}.items()}
    accepted = TunableOverlay(store, {'challengers_simulated': 2, 'open_candidate_count': 2}, tagged_fields=floors)
    harness = EvaluationHarness(sessions, accepted, repository=ROOT,
        hooks=(scaled_rival(1), DomainHook('fixture', (), advice=shop_and_threat_advice)))
    result = fit_margins(harness, {'fight_scale': [.25, 1, 2]}, draws=3, seed=17)
    fields, carried = result['fields'], result['carried']
    # The fixture Guide has no roll-down, so stage 3 gets its own key beside the sourced ones.
    assert fields['pivot_margin_by_stage']['default'] == .5 and fields['pivot_margin_by_stage']['post_roll_down'] == .8
    assert fields['pivot_margin_by_stage']['3'] >= .5
    assert result['diagnostics']['pivot_margin_by_stage']['3']['z'] == 2
    assert result['diagnostics']['pivot_margin_by_stage']['3']['available'] == 4
    assert fields['board_power_buy_min']['3'] >= .05
    assert fields['threat_share_on'] >= .5 and fields['threat_share_off'] <= .3
    for name in ('pivot_margin_by_stage', 'board_power_buy_min', 'threat_share_on', 'threat_share_off'):
        assert name not in carried
    # Unobserved guards stay carried with the reason, never a default fit.
    assert carried['comp_defining_margin'] == 'comp_commit_paired_guard_unavailable'
    assert carried['review_min_cost'] == 'compatible_paired_guard_unavailable'
    assert 'game_id' not in str(result)


def test_conditional_shared_prefix_components_keep_unequal_tape_covariance():
    from tft_harness.margins import MarginInput, estimate_margin
    # Four grant draws and two price draws share the first two random lanes.
    # MC variance is 1/3 + 1 + 1 = 7/3; model variance is 18.
    result = estimate_margin(MarginInput('wisp_buy_margin', '3', 'wisp', 'placement',
        TaggedValue(.1, 'default', 'Sourced starting floor', '2'), False,
        None, (-3, 3), 'Conditional grant and price on the shared prefix', 'Family-1 bootstrap',
        rollout_components=((0, 2, 0, 2), (0, 2))))
    assert result.mc_standard_error == pytest.approx(1.5275252316519468)
    assert result.value == pytest.approx(4.509249752822894)
    assert result.reason is None


@pytest.mark.parametrize('kind', ['unit_grant', 'risky'])
def test_default_engine_conditional_wisp_guard_retains_grant_and_short_price_tapes(tmp_path, kind):
    import tomllib
    import tomli_w
    from tests.test_replay_contracts import historical_data, log_snapshot, NOW, ROOT
    from tft_core.storage import SessionStore
    from tft_harness import EvaluationHarness
    from tft_harness.margins import paired_guards, replay_draws
    store, data = historical_data(tmp_path)
    path = tmp_path/'patch/static.toml'
    static = tomllib.loads(path.read_text())
    static['fields']['round_types']['value'] = {key: 'combat' for key in static['fields']['round_order']['value']}
    static['fields']['rules_flags']['value']['wisp_purchase_shop_slots_delta'] = 0
    static['fields']['rules_flags']['value']['item_slots_max'] = 3
    static['fields']['wisps']['value'] = {'grant': {'effect_kind': 'unit_grant', 'cost': 1,
        'offer_stages': [3], 'values': {'outcomes': [
            {'probability': .75, 'unit_ids': ['unit']},
            {'probability': .25, 'unit_ids': ['unit', 'unit']}]}}}
    if kind == 'risky':
        static['fields']['wisps']['value']['grant'].update(effect_kind='risky', values={'outcomes': [
            {'probability': .75, 'effect': {'effect_kind': 'gold', 'values': {'gold': 8}}},
            {'probability': .25, 'effect': {'effect_kind': 'gold', 'values': {'gold': 0}}}]})
    path.write_text(tomli_w.dumps(static))
    import json
    entities_path = path.parent/'entities.json'
    entities = json.loads(entities_path.read_text())
    entities['entities'][0]['values']['item_reference'] = {'value': 0, 'source': 'owner'}
    entities['entities'].append({'id': 'fixture-item', 'kind': 'item', 'name': 'Fixture item', 'values': {'category': {'value': 'finished', 'source': 'owner'}}})
    entities_path.write_text(json.dumps(entities))
    tunables_path = path.parent/'tunables.toml'
    tunables = tomllib.loads(tunables_path.read_text())
    tunables['fields']['component_income_by_stage']['value'] = {str(stage): {} for stage in range(1, 9)}
    tunables['fields']['component_discount_by_stage']['value'] = {str(stage): 0 for stage in range(1, 9)}
    tunables_path.write_text(tomli_w.dumps(tunables))
    from tests.test_replay_contracts import GuideFeed
    class ConditionalFeed(GuideFeed):
        name = 'conditional-guide-fixture'
        def fetch(self):
            value = super().fetch()
            value['guides'][0]['finalComp'][0]['items'] = ['fixture-item']
            return value
    data = store.refresh(path.parent, now=NOW, sources=(ConditionalFeed(),)).snapshot
    sessions = SessionStore(tmp_path/'logs', tmp_path/'config')
    sessions.start_game('901', set_id='18', patch=data.patch, data_snapshot_id=data.snapshot_id,
        timestamp=NOW.isoformat())
    sessions.append_event('snapshot', log_snapshot(data, gold=1, hp=7,
        pinned_line={'id': 'fixed-hold', 'levels': {}, 'rolls': {}}, wisp={'wisp_id': 'grant', 'slot': 4, 'cost': 1},
        wisp_complete=True, wisp_purchases_this_round=0, wisp_purchase_count_complete=True,
        item_bench=(), item_inventory_complete=True, held_augments=(), held_augments_complete=True),
        timestamp=NOW.isoformat())
    sessions.end_game(timestamp=NOW.isoformat())
    batch = replay_draws(EvaluationHarness(sessions, store, repository=ROOT), [{}])[0]
    record = next(record for record in batch[0].records if record.decision == 'wisp')
    assert record.advice['payload'].get('paused') is not True
    guards = paired_guards(batch, kind='wisp')
    assert len(guards) == 1
    assert tuple(map(len, guards[0].components)) == ((4, 2) if kind == 'unit_grant' else (4,))
    assert guards[0].mean == pytest.approx(record.advice['payload']['placement_gain'])
    assert guards[0].deterministic is False
    buy = next(option for option in record.options if option['action'] == 'buy')
    from tft_harness.margins import MarginInput, estimate_margin
    estimate = estimate_margin(MarginInput('wisp_buy_margin', '3', 'wisp', 'placement',
        TaggedValue(0, 'default', 'Fixture floor', '2'), False, None, (0, 0),
        'Actual Engine conditional tapes', 'Fixed-model control', rollout_components=guards[0].components))
    assert estimate.mc_standard_error == pytest.approx(buy['standard_error'])
    if kind == 'unit_grant':
        assert estimate.mc_standard_error > 0
    from tft_harness.margins import stage_margins
    draw_batches = replay_draws(EvaluationHarness(sessions, store, repository=ROOT),
        [{'fight_scale': .1}, {'fight_scale': 2}, {'fight_scale': 10}])
    draw_guards = [paired_guards(draw, kind='wisp') for draw in draw_batches]
    assert all(guard[0].key == guards[0].key for guard in draw_guards)
    stage = stage_margins(guards, draw_guards, target='wisp_buy_margin',
        floor=TaggedValue(0, 'default', 'Fixture floor', '2'), costly_or_sticky=False,
        rollout_citation='Actual conditional tapes', model_citation='Family-1 scale controls')
    assert stage['3']['available'] == 1
    if kind == 'unit_grant':
        assert stage['3']['value'] > 0


@pytest.mark.parametrize('citation', [None, False, 1])
def test_conditional_component_provenance_rejects_nontext_citations(citation):
    from tft_harness.margins import MarginInput
    with pytest.raises(DataError):
        MarginInput('wisp_buy_margin', '3', 'wisp', 'placement',
            TaggedValue(.1, 'default', 'Floor', '2'), False, None, (0, 1),
            citation, 'Model draws', rollout_components=((0, 1),))


@pytest.mark.parametrize('vectors', [(), ((0, 1),)*3, ((0, float('nan')),), ((False, 1),)])
def test_invalid_conditional_tapes_are_rejected(vectors):
    from tft_harness.margins import MarginInput
    with pytest.raises(DataError):
        MarginInput('wisp_buy_margin', '3', 'wisp', 'placement',
            TaggedValue(.1, 'default', 'Floor', '2'), False, None, (0, 1),
            'Conditional tape', 'Model draws', rollout_components=vectors)


def test_conditional_component_samples_are_immutable_and_short_samples_keep_floor():
    from tft_harness.margins import MarginInput, estimate_margin
    vectors = [[0, 2], [0, 2]]
    inputs = MarginInput('wisp_buy_margin', '3', 'wisp', 'placement',
        TaggedValue(.1, 'default', 'Floor', '2'), False, None, (0, 0),
        'Shared prefix', 'Fixed model', rollout_components=vectors)
    vectors[0][1] = 900
    assert estimate_margin(inputs).mc_standard_error == pytest.approx(2)
    short = replace(inputs, rollout_components=((1,), (1, 2)))
    result = estimate_margin(short)
    assert result.value == .1 and result.reason == 'insufficient_paired_rollouts'
