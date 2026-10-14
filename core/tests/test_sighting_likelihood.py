"""Joint trait-event predictions use the real inference prior, not marginal scores."""
from dataclasses import replace

import pytest

from tft_data import Entity, TaggedValue
from tft_engine import TraitSighting, infer_opponent
from tests.test_replay_contracts import historical_data


def deterministic_roster(tmp_path):
    _, data = historical_data(tmp_path)
    tag = lambda value: TaggedValue(value, 'owner', citation='Declared synthetic event model')
    entities = dict(data.entities)
    entities['unit'] = replace(entities['unit'], traits=('ice',))
    entities['fire-unit'] = Entity('fire-unit','unit','Synthetic fire unit',1,('fire',),
        values={'play_rate':tag(.5),'team_slot_cost':tag(1)})
    for identity in ('fire','ice'):
        entities[identity] = Entity(identity,'trait',identity,values={'breakpoints':tag([2])})
    return replace(data, entities=entities, tunables=dict(data.tunables)|{
        'emblem_slack_max':tag(0), 'emblem_count_prior':tag({'0':1}),
        'opponent_inference_state_cap':tag(8), # Bounded two-unit synthetic roster, including empty state.
        'sighting_persistence_weight':tag(2)})


def test_next_sighting_likelihood_normalizes_joint_boards_with_and_without_persistence(tmp_path):
    from tft_engine import predict_sighting

    data = deterministic_roster(tmp_path)
    old = TraitSighting('rival','3-2',1,{'fire':1})
    prior = infer_opponent(old, data)
    assert prior.certainty == 1 # Certainty of a conditioned posterior is not the event probability.
    next_fire = TraitSighting('rival','3-3',1,{'fire':1})
    next_ice = TraitSighting('rival','3-3',1,{'ice':1})
    fire = predict_sighting(next_fire, data, previous=prior)
    ice = predict_sighting(next_ice, data, previous=prior)
    assert fire.probability == pytest.approx(2/3)
    assert ice.probability == pytest.approx(1/3)
    assert fire.probability+ice.probability == pytest.approx(1)
    assert fire.reason is None and fire.model == 'normalized_unit_set_prior/zero-emblem/deterministic-form'
    assert predict_sighting(next_fire, data).probability == .5
    impossible = predict_sighting(TraitSighting('rival','3-3',1,{'fire':2}), data)
    assert impossible.probability == 0 and impossible.reason is None


def test_next_sighting_refuses_unsupported_latent_laws_and_future_or_other_player_history(tmp_path):
    from tft_engine import predict_sighting
    from tft_data import DataError

    data = deterministic_roster(tmp_path)
    sighting = TraitSighting('rival','3-3',1,{'fire':1})
    tag = lambda value: TaggedValue(value, 'owner')
    emblems = replace(data,tunables=dict(data.tunables)|{'emblem_slack_max':tag(2),
        'emblem_count_prior':tag({'0':1,'1':.1})})
    unsupported = predict_sighting(sighting, emblems)
    assert unsupported.probability is None and unsupported.reason == 'emblem_assignment_joint_law_unavailable'
    forms = replace(data,static=dict(data.static)|{'trait_rules':tag({'unit':{'replace':[{'ice':1},{'fire':1}]}})})
    assert predict_sighting(sighting, forms).reason == 'active_form_joint_law_unavailable'
    for old in (TraitSighting('someone-else','3-2',1,{'fire':1}), TraitSighting('rival','4-1',1,{'fire':1})):
        with pytest.raises(DataError,match='causal previous'):
            predict_sighting(sighting,data,previous=infer_opponent(old,data))
