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


def support_logs(tmp_path):
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
    tunables_path.write_text(tomli_w.dumps(tunables))
    refreshed = store.refresh(root, now=NOW+timedelta(seconds=1), sources=(PublicSupportFeed(),))
    assert refreshed.error is None
    data = refreshed.snapshot
    sessions = SessionStore(tmp_path/'logs',tmp_path/'config',live_installed=True)
    sessions.start_game('901',patch=data.patch,data_snapshot_id=data.snapshot_id,
        timestamp=(NOW+timedelta(seconds=2)).isoformat())
    sessions.append_event('sighting', {'opponent_id':'rival','round_id':'3-1','level':1,
        'traits':{'fire':1},'hidden_traits':0},timestamp=(NOW+timedelta(seconds=2.1)).isoformat())
    raw = log_snapshot(data, at=NOW+timedelta(seconds=2.2))
    sessions.append_event('snapshot', raw, timestamp=raw['captured_at'])
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
