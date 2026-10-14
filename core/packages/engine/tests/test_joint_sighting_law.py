"""Public joint-event scores use declared synthetic whole-board probabilities."""
from dataclasses import replace

import pytest

from tft_engine import Board, TraitSighting, Unit
from tft_data import DataError, Entity
from .test_planning import patch, tag


def roster():
    data = patch()
    entities = dict(data.entities)
    entities['b'] = replace(entities['b'], traits=('ice',))
    entities['ice'] = Entity('ice', 'trait', 'Ice', values={'breakpoints': tag([2])})
    return replace(data, entities=entities)


def test_joint_event_uses_declared_whole_board_weights_not_conditional_certainty():
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', 1, 'synthetic',
        'Explicit four-part synthetic support', (
            JointHypothesis(Board((Unit('a'),)), 2),
            JointHypothesis(Board((Unit('b'),)), 6),
        ))
    fire = predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}), data, law)
    ice = predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'ice': 1}), data, law)
    assert fire.probability == .25
    assert ice.probability == .75
    assert fire.reason is None and fire.source == 'synthetic'


def test_correlated_forms_and_emblems_score_complete_visible_and_hidden_trait_event():
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    entities = dict(data.entities)
    for trait in ('fire', 'ice'):
        entities[trait+'-emblem'] = Entity(trait+'-emblem', 'item', trait+' emblem',
            values={'trait_grants': tag({trait: 1})})
    data = replace(data, entities=entities, static=dict(data.static)|{
        'trait_rules': tag({'a': {'replace': [{'fire': 1}, {'ice': 1}]}})})
    forms = [{'fire': 1}]
    law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', 1, 'synthetic',
        'Declared correlated form/item support; no independent marginal law', (
            JointHypothesis(Board((Unit('a', items=('ice-emblem',)),)), 1, forms=forms),
            JointHypothesis(Board((Unit('a', items=('fire-emblem',)),)), 3, forms=({'ice': 1},)),
            JointHypothesis(Board((Unit('a'),)), 6, forms=({'fire': 1},)),
        ))
    forms[0]['fire'] = 9  # Caller mutations cannot change an accepted law.
    assert predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}, hidden_traits=1), data, law).probability == pytest.approx(.4)
    assert predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}), data, law).probability == pytest.approx(.6)
    assert predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'fire': 2}), data, law).probability == 0


@pytest.mark.parametrize('field,value', [('snapshot_id', 'other'), ('opponent_id', 'other'),
    ('round_id', '3-3'), ('level', 2), ('source', ''), ('citation', '')])
def test_joint_law_cannot_cross_snapshot_player_round_level_or_lack_provenance(field, value):
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    with pytest.raises(DataError):
        law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', 1, 'synthetic',
            'Declared support', (JointHypothesis(Board((Unit('a'),)), 1),))
        law = replace(law, **{field: value})
        predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}), data, law)


@pytest.mark.parametrize('weight', [True, -1, float('nan'), float('inf'), 0])
def test_joint_support_rejects_invalid_or_zero_total_mass(weight):
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    with pytest.raises(DataError):
        law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', 1, 'synthetic',
            'Declared support', (JointHypothesis(Board((Unit('a'),)), weight),))
        predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}), data, law)


def test_finite_extreme_weights_normalize_without_overflow_and_absent_law_is_unavailable():
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    sighting = TraitSighting('rival', '3-2', 1, {'fire': 1})
    law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', 1, 'synthetic',
        'Declared extreme weights', (
            JointHypothesis(Board((Unit('a'),)), 1e308),
            JointHypothesis(Board((Unit('b'),)), 1e308),
        ))
    assert predict_joint_sighting(sighting, data, law).probability == .5
    unavailable = predict_joint_sighting(sighting, data, None)
    assert unavailable.probability is None and unavailable.reason == 'joint_sighting_law_unavailable'


def test_joint_law_capacity_uses_the_certified_active_form_not_a_maximum_over_forms():
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    data = replace(data, entities=dict(data.entities)|{'fire': replace(data.entities['fire'], values={'breakpoints': tag([1])})})
    capacity = dict(data.value('team_capacity')) | {
        'trait_bonuses': [{'trait_id': 'fire', 'breakpoint': 1, 'slots': 1, 'activation': 'continuous'}]}
    data = replace(data, static=dict(data.static)|{
        'team_capacity': tag(capacity),
        'trait_rules': tag({'a': {'replace': [{'fire': 1}, {'ice': 1}]}})})
    legal = JointHypothesis(Board((Unit('a'), Unit('b'))), 1, forms=({'fire': 1}, {'ice': 1}))
    law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', 1, 'synthetic', 'Declared forms', (legal,))
    assert predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}, hidden_traits=1), data, law).probability == 1
    illegal = JointHypothesis(Board((Unit('a'), Unit('b'))), 1, forms=({'ice': 1}, {'ice': 1}))
    with pytest.raises(DataError, match='team slots'):
        predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'ice': 2}), data, replace(law, hypotheses=(illegal,)))


@pytest.mark.parametrize('case', ['unknown_unit', 'unknown_trait', 'boolean_grant', 'conflicting_forms', 'boolean_level'])
def test_joint_law_rejects_unsupported_or_conflicting_support_without_a_probability(case):
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    board = Board((Unit('a'),))
    forms = None
    level = 1
    if case == 'unknown_unit':
        board = Board((Unit('missing'),))
    elif case in ('unknown_trait', 'boolean_grant'):
        grants = {'missing': 1} if case == 'unknown_trait' else {'fire': True}
        item = Entity('bad-emblem', 'item', 'Unsupported emblem', values={'trait_grants': tag(grants)})
        data = replace(data, entities=dict(data.entities)|{item.id: item})
        board = Board((Unit('a', items=(item.id,)),))
    elif case == 'conflicting_forms':
        data = replace(data, static=dict(data.static)|{
            'trait_rules': tag({'a': {'replace': [{'fire': 1}, {'ice': 1}]}})})
        board = Board((Unit('a'), Unit('a')))
        forms = ({'fire': 1}, {'ice': 1})
        level = 2
    else:
        level = True
    with pytest.raises(DataError):
        law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', level, 'synthetic',
            'Declared support', (JointHypothesis(board, 1, forms=forms),))
        predict_joint_sighting(TraitSighting('rival', '3-2', level, {'fire': 1}), data, law)


def test_positive_underflow_event_keeps_finite_log_score_distinct_from_impossible_event():
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', 1, 'synthetic',
        'Declared extreme finite prior', (
            JointHypothesis(Board((Unit('a'),)), 1e308),
            JointHypothesis(Board((Unit('b'),)), 1e-300),
        ))
    rare = predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'ice': 1}), data, law)
    impossible = predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'ice': 2}), data, law)
    assert rare.probability == 0  # Float representation underflows, not a zero-mass law.
    assert rare.log_probability == pytest.approx(-1399.9717365403804)
    assert impossible.probability == 0 and impossible.log_probability is None


def test_source_certified_inventory_capacity_and_observed_budget_are_joint_events():
    from tft_engine.capacity import CapacityEvidence
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    extra = Entity('extra-slot', 'item', 'Extra slot', values={'trait_grants': tag({})})
    entities = dict(data.entities)|{extra.id: extra}
    entities['a'] = replace(entities['a'], values=dict(entities['a'].values)|{'team_slot_cost': tag(2)})
    capacity = dict(data.value('team_capacity'))|{
        'inventory_item_slots': {extra.id: {'slots': 1, 'activation': 'continuous', 'scope': 'owned'}}}
    data = replace(data, entities=entities, static=dict(data.static)|{'team_capacity': tag(capacity)})
    law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', 1, 'synthetic', 'Correlated capacity inventory', (
        JointHypothesis(Board((Unit('a'),)), 4, capacity=CapacityEvidence(item_bench=(extra.id,))),
        JointHypothesis(Board((Unit('b'),)), 6, capacity=CapacityEvidence(item_bench=())),
    ))
    assert predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}, team_slot_budget=2), data, law).probability == pytest.approx(.4)
    assert predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}, team_slot_budget=1), data, law).probability == 0
    assert predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'ice': 1}, team_slot_budget=1), data, law).probability == pytest.approx(.6)
    missing_inventory = replace(law.hypotheses[0], capacity=CapacityEvidence())
    with pytest.raises(DataError, match='Complete item inventory'):
        predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}), data, replace(law, hypotheses=(missing_inventory,)))


@pytest.mark.parametrize('change', [{'board': {}}, {'capacity': {}}])
def test_joint_support_cannot_retain_untyped_mutable_board_or_inventory(change):
    from tft_engine.joint_sighting_law import JointHypothesis

    with pytest.raises(DataError):
        JointHypothesis(**({'board': Board((Unit('a'),)), 'weight': 1} | change))


def test_certain_event_has_zero_log_loss_even_with_extreme_total_weight():
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', 1, 'synthetic',
        'Every declared outcome has one fire unit', tuple(
            JointHypothesis(Board((Unit(identity),)), 1e308) for identity in ('a', 'c', 'd')))
    prediction = predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}), data, law)
    assert prediction.probability == 1 and prediction.log_probability == 0


@pytest.mark.parametrize('level', [True, 1.0])
def test_law_level_cannot_alias_valid_integer_sighting_context(level):
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    with pytest.raises(DataError, match='level'):
        law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', level, 'synthetic',
            'Declared support', (JointHypothesis(Board((Unit('a'),)), 1),))
        predict_joint_sighting(TraitSighting('rival', '3-2', 1, {'fire': 1}), data, law)


def test_item_grants_require_positive_counts_while_explicit_empty_certificate_is_valid():
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    item = Entity('item', 'item', 'Certified item', values={'trait_grants': tag({'fire': 0})})
    data = replace(data, entities=dict(data.entities)|{item.id: item})
    law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', 1, 'synthetic',
        'Declared item assignment', (JointHypothesis(Board((Unit('a', items=(item.id,)),)), 1),))
    sighting = TraitSighting('rival', '3-2', 1, {'fire': 1})
    with pytest.raises(DataError, match='grant'):
        predict_joint_sighting(sighting, data, law)
    data = replace(data, entities=dict(data.entities)|{item.id: replace(item, values={'trait_grants': tag({})})})
    assert predict_joint_sighting(sighting, data, law).probability == 1


@pytest.mark.parametrize('board', [Board(({'unit_id': 'a'},)), Board((), ({'unit_id': 'a'},)),
    Board((Unit({'id': 'a'}),)), Board((Unit('a', items=({'item_id': 'x'},)),)),
    Board((Unit('a', position={'x': 1}),)), Board((Unit('a', stars=True),))])
def test_hypothesis_rejects_mutable_or_untyped_nested_unit_state(board):
    from tft_engine.joint_sighting_law import JointHypothesis

    with pytest.raises(DataError):
        JointHypothesis(board, 1)


@pytest.mark.parametrize('traits,hidden', [({'fire': True}, 0), ({'fire': 1.0}, 0),
    ({'fire': 1}, 0.0), ({'fire': 1}, False)])
def test_joint_event_rejects_nonintegral_recorded_trait_truth(traits, hidden):
    from tft_engine.joint_sighting_law import JointHypothesis, JointSightingLaw, predict_joint_sighting

    data = roster()
    law = JointSightingLaw(data.snapshot_id, 'rival', '3-2', 1, 'synthetic',
        'Declared whole-board support', (JointHypothesis(Board((Unit('a'),)), 1),))
    with pytest.raises(DataError):
        predict_joint_sighting(TraitSighting('rival', '3-2', 1, traits, hidden), data, law)
