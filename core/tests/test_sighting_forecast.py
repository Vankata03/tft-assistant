"""Predictive trait likelihood uses declared joint support before target truth."""
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from tests.test_replay_contracts import historical_data
from tft_data import Entity, SourceState, TaggedValue
from tft_engine import Board, TraitSighting, Unit


PUBLISHED = datetime(2026, 10, 11, tzinfo=UTC)


def support_data(tmp_path):
    _, data = historical_data(tmp_path)
    entities = dict(data.entities)
    entities['unit'] = replace(entities['unit'], traits=('fire',))
    entities['ice-unit'] = replace(entities['unit'], id='ice-unit', traits=('ice',))
    for trait in ('fire', 'ice'):
        entities[trait] = Entity(trait, 'trait', trait, values={'breakpoints': TaggedValue([2], 'owner')})
    cohort = {'minimum_rank': 'DIAMOND', 'regions': 'all'}
    provider = SourceState('public-fixture', data.patch, PUBLISHED, PUBLISHED, 'statistics', cohort=cohort)
    rows = [{'weight': 1, 'board': Board((Unit('unit'),)).to_dict()},
        {'weight': 3, 'board': Board((Unit('ice-unit'),)).to_dict()}]
    declaration = {'provider': provider.name, 'patch': data.patch, 'cohort': cohort,
        'source_updated_at': PUBLISHED.isoformat(), 'rounds': {'3-2': {'1': rows}}}
    return replace(data, entities=entities, sources={provider.name: provider},
        tunables=dict(data.tunables)|{'sighting_persistence_weight': TaggedValue(2, 'owner',
            'Synthetic doubled persistence worked example', '1')},
        static=dict(data.static)|{'opponent_joint_support': TaggedValue(declaration, 'owner',
            'Declared synthetic public joint-support fixture')})


def test_snapshot_support_produces_target_independent_joint_law_and_persistence_baseline(tmp_path):
    from tft_review.sighting_forecast import sighting_law
    from tft_engine.joint_sighting_law import predict_joint_sighting
    from tft_engine.opponents import InferredBoard

    data = support_data(tmp_path)
    previous = InferredBoard('rival', '3-1', 1, {'unit': 1, 'ice-unit': 0}, 1, 1)
    qualified = sighting_law(data, opponent_id='rival', round_id='3-2', level=1, previous=previous)
    naive = sighting_law(data, opponent_id='rival', round_id='3-2', level=1,
        previous=previous, persistence=False)
    fire = TraitSighting('rival', '3-2', 1, {'fire': 1})
    ice = TraitSighting('rival', '3-2', 1, {'ice': 1})
    assert predict_joint_sighting(fire, data, qualified).probability == pytest.approx(.4)
    assert predict_joint_sighting(ice, data, qualified).probability == pytest.approx(.6)
    assert predict_joint_sighting(fire, data, naive).probability == .25
    assert qualified.snapshot_id == data.snapshot_id
    assert qualified.citation == 'Declared synthetic public joint-support fixture'
    assert qualified.source == 'public-fixture'


def test_forecast_preserves_finite_log_underflow_and_distinguishes_real_zero_event(tmp_path):
    from tft_review.sighting_forecast import forecast_sighting
    from math import isfinite

    data = support_data(tmp_path)
    raw = dict(data.static['opponent_joint_support'].value)
    raw['rounds'] = {'3-2': {'1': [
        {'weight': 1e-300, 'board': Board((Unit('unit'),)).to_dict()},
        {'weight': 1e308, 'board': Board((Unit('ice-unit'),)).to_dict()}]}}
    data = replace(data, static=dict(data.static)|{'opponent_joint_support': TaggedValue(raw,
        'owner', 'Declared rare synthetic event')})
    rare = forecast_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}), data)
    impossible = forecast_sighting(TraitSighting('rival', '3-2', 1, {'fire': 2}), data)
    assert rare.probability == 0
    assert isfinite(rare.log_probability)
    assert rare.log_probability == pytest.approx(-1399.9717365403804)
    assert impossible.probability == 0 and impossible.log_probability is None
    assert rare.reason is impossible.reason is None


def test_persistence_keeps_finite_source_support_when_reweighted_mass_overflows(tmp_path):
    from math import log
    from tft_engine.opponents import InferredBoard
    from tft_review.contracts import json_value
    from tft_review.sighting_forecast import forecast_sighting

    data = support_data(tmp_path)
    raw = json_value(data.static['opponent_joint_support'].value)
    for row in raw['rounds']['3-2']['1']:
        row['weight'] = 1e308
    data = replace(data, static=dict(data.static)|{'opponent_joint_support':
        TaggedValue(raw, 'owner', 'Finite equal-mass synthetic support')})
    previous = InferredBoard('rival', '3-1', 1, {'unit': 1, 'ice-unit': 0}, 1, 1)
    target = TraitSighting('rival', '3-2', 1, {'fire': 1})
    predicted = forecast_sighting(target, data, previous=previous)
    naive = forecast_sighting(target, data, previous=previous, persistence=False)
    assert predicted.reason is naive.reason is None
    # Doubling fire mass against unchanged ice mass gives 2:1 odds.
    assert predicted.probability == pytest.approx(2/3)
    assert predicted.log_probability == pytest.approx(log(2/3))
    assert naive.probability == .5


def test_persistence_retains_positive_subnormal_mass_as_finite_log_score(tmp_path):
    from math import isfinite
    from tft_engine.opponents import InferredBoard
    from tft_review.contracts import frozen_json, json_value
    from tft_review.sighting_forecast import forecast_sighting, sighting_law
    from tft_engine.joint_sighting_law import predict_joint_sighting

    data = support_data(tmp_path)
    raw = json_value(data.static['opponent_joint_support'].value)
    raw['rounds']['3-2']['1'][0]['weight'] = 5e-324
    raw['rounds']['3-2']['1'][1]['weight'] = 1
    data = replace(data, static=dict(data.static)|{'opponent_joint_support':
        TaggedValue(raw, 'owner', 'Positive subnormal synthetic support')},
        tunables=dict(data.tunables)|{'sighting_persistence_weight':
            TaggedValue(.5, 'owner', 'Synthetic halved persistence', '1')})
    previous = InferredBoard('rival', '3-1', 1, {'unit': 1, 'ice-unit': 0}, 1, 1)
    target = TraitSighting('rival', '3-2', 1, {'fire': 1})
    predicted = forecast_sighting(target, data, previous=previous)
    law = sighting_law(data, opponent_id='rival', round_id='3-2', level=1, previous=previous)
    assert predicted.reason is None
    assert predicted.log_probability == pytest.approx(-745.1332191019411)
    assert isfinite(predicted.log_probability)
    assert predict_joint_sighting(target, data, law) == predicted
    assert frozen_json(law)['hypotheses'][0]['log_weight'] == pytest.approx(-745.1332191019411)
    with pytest.raises(TypeError):
        frozen_json(law)['hypotheses'][0]['weight'] = 0


@pytest.mark.parametrize('invalid', ['unqualified_source', 'different_patch', 'missing_cohort',
    'different_update', 'missing_context', 'bool_weight'])
def test_unqualified_or_malformed_support_never_silently_becomes_a_uniform_law(tmp_path, invalid):
    from tft_review.sighting_forecast import forecast_sighting
    from tft_review.contracts import json_value

    data = support_data(tmp_path)
    raw = json_value(data.static['opponent_joint_support'].value)
    state = data.sources['public-fixture']
    if invalid == 'unqualified_source': state = replace(state, qualified=False)
    elif invalid == 'different_patch': raw['patch'] = 'other'
    elif invalid == 'missing_cohort': raw['cohort'] = {}
    elif invalid == 'different_update': raw['source_updated_at'] = '2020-01-01T00:00:00+00:00'
    elif invalid == 'missing_context': raw['rounds'] = {}
    elif invalid == 'bool_weight': raw['rounds']['3-2']['1'][0]['weight'] = True
    data = replace(data, sources={state.name: state}, static=dict(data.static)|{
        'opponent_joint_support': TaggedValue(raw, 'owner', 'Synthetic declaration')})
    prediction = forecast_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}), data)
    assert prediction.probability is None and prediction.log_probability is None
    assert prediction.reason is not None


class PublicSupportFeed:
    """Explicit external-source fixture; no current provider response is claimed."""
    name, kind = 'public-fixture', 'statistics'

    def metadata(self):
        return SourceState(self.name, 'fixture', PUBLISHED, PUBLISHED, self.kind,
            cohort={'minimum_rank': 'DIAMOND', 'regions': 'all'})

    def fetch(self):
        return {'rows': []}


def support_logs(tmp_path, *, intermediate=(), mode='silent'):
    import json
    import tomllib
    import tomli_w
    from datetime import timedelta
    from tft_core.storage import SessionStore
    from tests.test_replay_contracts import NOW, log_snapshot

    store, _ = historical_data(tmp_path)
    # These are reviewed synthetic external inputs in an isolated temporary patch.
    root = tmp_path/'patch'
    entities_path = root/'entities.json'
    rows = json.loads(entities_path.read_text())['entities']
    rows[0]['traits'] = ['fire']
    rows += [dict(rows[0], id='ice-unit', traits=['ice']),
        {'id':'fire','name':'Fire','kind':'trait','values':{'breakpoints':{'value':[2],'source':'owner'}}},
        {'id':'ice','name':'Ice','kind':'trait','values':{'breakpoints':{'value':[2],'source':'owner'}}}]
    entities_path.write_text(json.dumps({'entities':rows}))
    declarations = {'provider':'public-fixture','patch':'fixture',
        'cohort':{'minimum_rank':'DIAMOND','regions':'all'},
        'source_updated_at':PUBLISHED.isoformat(), 'rounds':{'3-2':{'1':[
            {'weight':1,'board':{'units':[{'unit_id':'unit'}]}},
            {'weight':3,'board':{'units':[{'unit_id':'ice-unit'}]}}]}}}
    static_path = root/'static.toml'
    static = tomllib.loads(static_path.read_text())
    static['fields']['opponent_joint_support'] = {'value':declarations,'source':'owner',
        'citation':'Declared external synthetic support'}
    static_path.write_text(tomli_w.dumps(static))
    tunables_path = root/'tunables.toml'
    tunables = tomllib.loads(tunables_path.read_text())
    tunables['fields']['sighting_persistence_weight']['value'] = 2
    tunables['fields']['emblem_slack_max']['value'] = 0
    tunables['fields']['opponent_inference_state_cap']['value'] = 64
    tunables_path.write_text(tomli_w.dumps(tunables))
    refreshed = store.refresh(root, now=NOW+timedelta(seconds=1), sources=(PublicSupportFeed(),))
    assert refreshed.error is None
    data = refreshed.snapshot
    sessions = SessionStore(tmp_path/'logs',tmp_path/'config',live_installed=True)
    sessions.set_mode(mode)
    sessions.start_game('901',patch=data.patch,data_snapshot_id=data.snapshot_id,
        timestamp=(NOW+timedelta(seconds=2)).isoformat())
    sessions.append_event('sighting', {'opponent_id':'rival','round_id':'3-1','level':1,
        'traits':{'fire':1},'hidden_traits':0},timestamp=(NOW+timedelta(seconds=2.1)).isoformat())
    raw = log_snapshot(data, at=NOW+timedelta(seconds=2.2))
    sessions.append_event('snapshot', raw, timestamp=raw['captured_at'])
    for kind, payload, seconds in intermediate:
        sessions.append_event(kind, payload, timestamp=(NOW+timedelta(seconds=seconds)).isoformat())
    target = sessions.append_event('sighting', {'opponent_id':'rival','round_id':'3-2','level':1,
        'traits':{'fire':1},'hidden_traits':0},timestamp=(NOW+timedelta(seconds=2.3)).isoformat())
    sessions.end_game(placement=4,timestamp=(NOW+timedelta(seconds=3)).isoformat())
    return sessions,store,data,target


def test_actual_harness_scores_next_sighting_against_same_support_without_persistence(tmp_path):
    from math import log
    from tests.test_replay_contracts import ROOT
    from tft_harness import EvaluationHarness

    sessions, store, data, target = support_logs(tmp_path)
    report = EvaluationHarness(sessions,store,repository=ROOT).evaluate()
    metric = report.metrics['next_sighting_log_loss']
    assert metric['value'] == pytest.approx(-log(.4))
    assert metric['naive']['value'] == pytest.approx(-log(.25))
    assert metric['eligible_rows'] == metric['eligible_games'] == 1
    assert metric['excluded']['no_causal_previous_sighting'] == 1
    assert report.examples == () # A locked Silent game has aggregates only.
    assert report.provenance['sighting_naive'] == 'same joint support; persistence disabled'
    assert store.get(data.snapshot_id).snapshot_id == data.snapshot_id


def test_harness_conditions_each_sighting_on_earlier_log_events_after_last_snapshot(tmp_path):
    from tests.test_replay_contracts import ROOT
    from tft_harness import EvaluationHarness
    from tft_review import ReplayProducer

    sessions, store, data, target = support_logs(tmp_path, mode='live', intermediate=((
        'sighting', {'opponent_id':'rival','round_id':'3-2','level':1,
            'traits':{'ice':1},'hidden_traits':0}, 2.25),))
    batch = ReplayProducer(sessions,store,repository=ROOT).produce('901')
    report = EvaluationHarness(sessions,store,repository=ROOT).evaluate()
    rows = [row for row in report.examples if row['metric'] == 'next_sighting_log_loss']
    # Ice is first forecast with fire persistence (.6); then fire with ice persistence (1/7).
    assert [row['prediction'] for row in rows] == pytest.approx([.6, 1/7])
    assert report.metrics['next_sighting_log_loss']['value'] == pytest.approx(1.228367886410652)
    assert rows[-1]['previous_round_id'] == '3-2'
    assert rows[-1]['prefix_through_seq'] == target['seq']-1
    assert rows[-1]['seed'] == batch.contexts[0].seed
    assert rows[-1]['data_snapshot_id'] == data.snapshot_id


def test_harness_discards_pre_gap_inference_between_snapshot_and_target(tmp_path):
    from datetime import timedelta
    from tests.test_replay_contracts import NOW, ROOT
    from tft_harness import EvaluationHarness

    sessions, store, _, _ = support_logs(tmp_path, intermediate=(('capture_gap', {
        'start':(NOW+timedelta(seconds=2.21)).isoformat(),
        'end':(NOW+timedelta(seconds=2.24)).isoformat(),'reason':'fixture_gap'}, 2.24),))
    report = EvaluationHarness(sessions,store,repository=ROOT).evaluate()
    metric = report.metrics['next_sighting_log_loss']
    assert metric['eligible_rows'] == 0
    assert metric['excluded']['no_causal_previous_sighting'] == 2


@pytest.mark.parametrize('prior_at,expected', [(2.3, 1/7), (2.4, .4)])
def test_harness_respects_both_commit_order_and_target_timestamp(tmp_path, prior_at, expected):
    from tests.test_replay_contracts import ROOT
    from tft_harness import EvaluationHarness

    sessions, store, _, target = support_logs(tmp_path, mode='live', intermediate=((
        'sighting', {'opponent_id':'rival','round_id':'3-2','level':1,
            'traits':{'ice':1},'hidden_traits':0}, prior_at),))
    report = EvaluationHarness(sessions,store,repository=ROOT).evaluate()
    row = next(row for row in report.examples if row['observation_seq'] == target['seq'])
    assert row['prediction'] == pytest.approx(expected)


def test_harness_excludes_target_inside_a_committed_capture_gap(tmp_path):
    from datetime import timedelta
    from tests.test_replay_contracts import NOW, ROOT
    from tft_harness import EvaluationHarness

    sessions, store, _, _ = support_logs(tmp_path, intermediate=(('capture_gap', {
        'start':(NOW+timedelta(seconds=2.21)).isoformat(),
        'end':(NOW+timedelta(seconds=2.35)).isoformat(),'reason':'fixture_gap'}, 2.25),))
    report = EvaluationHarness(sessions,store,repository=ROOT).evaluate()
    metric = report.metrics['next_sighting_log_loss']
    assert metric['eligible_rows'] == 0
    assert metric['excluded']['capture_gap'] == 1
