"""Public Engine examples with declared synthetic capacity rules."""
from dataclasses import replace
import pytest
from tft_data import DataError
from tft_engine import Board, Unit, estimate_strength, evaluate, GameHistory
from .test_planning import patch, snapshot, tag
from tft_data.models import Entity
from tft_engine.capacity import CapacityEvidence
from tft_engine import infer_opponent, TraitSighting


def capacity_data():
    data=patch()
    entities={id:replace(e,values=dict(e.values)|({'team_slot_cost':tag(2 if id=='c' else 1)} if e.kind=='unit' else {}))
        for id,e in data.entities.items()}
    return replace(data,entities=entities,static=dict(data.static)|{'team_capacity':tag({
        'levels':{str(level):level for level in range(1,11)},'trait_bonuses':(),
        'held_augment_slots':{},'inventory_item_slots':{},'transition_policy':{'deploy':'reserve_before','swap':'remove_then_reserve','bench':'validate_after'}})})


def test_public_power_rejects_one_two_slot_unit_on_a_one_slot_budget():
    data=capacity_data()
    with pytest.raises(DataError,match='team slots'):
        estimate_strength(Board((Unit('c'),)),1,data)
    assert estimate_strength(Board((Unit('c'),)),2,data).power>0


def test_public_advice_selects_ordinary_unit_when_stronger_two_slot_unit_cannot_fit():
    data=capacity_data();owned=Board((),(Unit('c'),Unit('a')))
    state=snapshot('2-3',board=owned,bench=owned.bench,level=1,gold=0)
    report=evaluate(state,GameHistory(),data,'review')
    assert tuple(u.unit_id for u in report.recommended_board.units)==('a',)
    assert tuple(u.unit_id for u in report.recommended_board.bench)==('c',)


@pytest.mark.parametrize('scope,holder,loose,legal',[
    ('deployed_equipment','bench',(),False),
    ('equipped_anywhere','bench',(),True),
    ('equipped_anywhere','none',('capacity_item',),False),
    ('owned','none',('capacity_item',),True),
    ('deployed_equipment','deployed',(),True),
])
def test_public_power_distinguishes_capacity_item_activation(scope,holder,loose,legal):
    data=capacity_data()
    item=Entity('capacity_item','item','Capacity item',values={'component':tag(False),'trait_grants':tag({})})
    rules=dict(data.value('team_capacity'))|{'inventory_item_slots':{'capacity_item':{'slots':1,'activation':'continuous','scope':scope}}}
    data=replace(data,entities=dict(data.entities)|{item.id:item},static=dict(data.static)|{'team_capacity':tag(rules)})
    units=(Unit('a',items=('capacity_item',) if holder=='deployed' else ()),Unit('b'))
    bench=(Unit('d',items=('capacity_item',)),) if holder=='bench' else ()
    board=Board(units,bench)
    if legal:
        assert estimate_strength(board,1,data,capacity=CapacityEvidence(item_bench=loose)).power>0
    else:
        with pytest.raises(DataError,match='team slots'):
            estimate_strength(board,1,data,capacity=CapacityEvidence(item_bench=loose))


def test_public_power_rejects_trait_capacity_not_supported_by_current_units():
    data=capacity_data()
    rules=dict(data.value('team_capacity'))|{'trait_bonuses':({'trait_id':'fire','breakpoint':2,'slots':1,'activation':'continuous'},)}
    entities=dict(data.entities);entities['b']=replace(entities['b'],traits=())
    data=replace(data,entities=entities,static=dict(data.static)|{'team_capacity':tag(rules)})
    with pytest.raises(DataError,match='trait capacity'):
        estimate_strength(Board((Unit('a'),Unit('b')),trait_counts={'fire':2}),1,data)
    assert estimate_strength(Board((Unit('a'),Unit('d'))),1,data).power>0


@pytest.mark.parametrize('identities',[('a','b'),('a','a')])
def test_public_transition_reserves_both_slots_before_deploying_large_unit(identities):
    data=capacity_data();owned=Board(tuple(Unit(id) for id in identities),(Unit('c',3),))
    state=snapshot('2-3',board=owned,bench=owned.bench,level=2,comp_lock='B',gold=0)
    report=evaluate(state,GameHistory(),data,'review')
    move=next(a for a in report.advice if a.decision=='transition' and a.option_id=='transition')
    assert tuple(u.unit_id for u in report.recommended_board.units)==('c',)
    steps=move.payload['steps']
    assert steps[0]['operation']=='bench'
    assert steps[-1]['operation']=='swap'
    assert {step['out_index'] for step in steps if step['out_index'] is not None}=={0,1}
    assert all(step['after']['occupied_slots']<=step['after']['maximum_slots'] for step in steps)
    assert all(step['after']['bench_units']<=9 for step in steps)


def test_public_inference_excludes_a_two_slot_unit_from_a_one_slot_budget():
    data=capacity_data()
    result=infer_opponent(TraitSighting('opponent','2-3',1,{'fire':1}),data)
    assert result.probabilities.get('c',0)==0
    assert result.probabilities['a']>0


def test_public_inference_uses_sourced_trait_capacity_without_inventing_units():
    data=capacity_data()
    rules=dict(data.value('team_capacity'))|{'trait_bonuses':({'trait_id':'fire','breakpoint':2,'slots':1,'activation':'continuous'},)}
    data=replace(data,static=dict(data.static)|{'team_capacity':tag(rules)},
        tunables=dict(data.tunables)|{'emblem_slack_max':tag(0),'size_level_prior':tag({'1':{'2':1}})})
    result=infer_opponent(TraitSighting('opponent','2-3',1,{'fire':2}),data)
    assert result.candidate_count==3 # pairs among a,b,d; c would exceed two slots.
    assert sum(result.probabilities.values())==pytest.approx(2)


def test_public_forced_guide_obeys_slots_and_transition_budget_exhaustion_pauses():
    data=capacity_data();owned=Board((Unit('a'),Unit('b')),(Unit('c',3),Unit('d')))
    state=snapshot('4-2',board=owned,bench=owned.bench,level=2,comp_lock='B',gold=0)
    result=evaluate(state,GameHistory(),data,'review')
    assert tuple(unit.unit_id for unit in result.recommended_board.units)==('c',)
    limited=replace(data,tunables=dict(data.tunables)|{'capacity_transition_state_cap':tag(1)})
    unavailable=evaluate(state,GameHistory(),limited,'review')
    assert unavailable.recommended_board is None and not unavailable.line_results
    assert any('search budget exhausted' in str(a.payload.get('reason','')) for a in unavailable.advice)


def test_public_choice_unit_grant_cannot_deploy_a_large_unit_without_room():
    from .test_decisions import item_patch
    data=item_patch();entities=dict(data.entities)
    entities['c']=replace(entities['c'],values=dict(entities['c'].values)|{'team_slot_cost':tag(2)})
    data=replace(data,entities=entities,static=dict(data.static)|{
        'wisps':tag({'grant':{'effect_kind':'unit_grant','values':{'outcomes':({'probability':1.0,'unit_ids':('c',)},)}}}),
        'wisp_round_cap':tag({'default':1,'trait_overrides':{}}),
        'round_types':tag({round_id:'combat' for round_id in data.value('round_order')}),
        'xp_table':tag({str(level):100000 for level in range(1,10)})},
        tunables=dict(data.tunables)|{'wisp_buy_margin':tag(0)})
    state=snapshot('3-2',board=Board((Unit('a'),)),bench=(),level=1,gold=0,hp=10,comp_lock='A',
        pinned_line={'id':'hold','levels':{},'rolls':{}},item_bench=(),item_inventory_complete=True,
        wisp={'wisp_id':'grant','slot':4,'cost':0},wisp_complete=True,slot_count=4,
        wisp_purchases_this_round=0,wisp_purchase_count_complete=True)
    result=evaluate(state,GameHistory(),data,'review',seed=123)
    offer=next(a for a in result.advice if a.decision=='wisp')
    assert not offer.payload.get('paused')
    record=offer.options[0].payload['outcomes'][0]
    before=next(row for row in record['before_lines']['A'] if row['line']['id']=='hold')
    after=next(row for row in record['after_lines']['A'] if row['line']['id']=='hold')
    assert before['seed']==after['seed']
    assert before['projections'][0]['hp']==after['projections'][0]['hp']
    assert after['projections'][0]['gold']>=before['projections'][0]['gold']
    assert before['rollout_deaths']==after['rollout_deaths']


def test_public_polymorph_pauses_when_deployed_outcome_overflows_without_rule():
    from .test_decisions import item_patch
    data=item_patch();entities=dict(data.entities)
    entities['c']=replace(entities['c'],values=dict(entities['c'].values)|{'team_slot_cost':tag(2)})
    effect={'effect_kind':'polymorph','values':{'eligible_costs':(1,),'target':'highest_star','cost_delta':2,
        'preserve_stars':True,'preserve_items':True,'outcomes':{'3':({'probability':1.0,'unit_id':'c'},)}}}
    data=replace(data,entities=entities,static=dict(data.static)|{'wisps':tag({'morph':effect}),
        'wisp_round_cap':tag({'default':1,'trait_overrides':{}})},tunables=dict(data.tunables)|{'wisp_buy_margin':tag(0)})
    state=snapshot(board=Board((Unit('a'),)),bench=(),level=1,gold=0,item_bench=(),item_inventory_complete=True,
        wisp={'wisp_id':'morph','slot':4,'cost':0},wisp_complete=True,slot_count=4,
        wisp_purchases_this_round=0,wisp_purchase_count_complete=True)
    option=next(a for a in evaluate(state,GameHistory(),data,'review').advice if a.decision=='wisp')
    assert option.payload.get('paused') is True
    assert 'capacity overflow' in option.payload['reason']


def test_public_lines_preserve_an_already_legal_trait_supported_board_on_same_tape():
    from tft_engine import simulate_lines, Line
    data=capacity_data();rules=dict(data.value('team_capacity'))
    rules['trait_bonuses']=({'trait_id':'fire','breakpoint':2,'slots':1,'activation':'continuous'},)
    data=replace(data,static=dict(data.static)|{'team_capacity':tag(rules),
        'round_types':tag({round_id:'combat' for round_id in data.value('round_order')}),
        'xp_table':tag({str(level):100000 for level in range(1,10)})})
    units=Board((Unit('a'),Unit('d')))
    state=snapshot('2-3',board=units,bench=(),level=1,gold=0,hp=10)
    reference=dict(rules)|{'levels':dict(rules['levels'])|{'1':2},'trait_bonuses':()}
    reference_data=replace(data,static=dict(data.static)|{'team_capacity':tag(reference)})
    actual=simulate_lines(state,GameHistory(),data,'A',(Line('hold'),),seed=123)
    expected=simulate_lines(state,GameHistory(),reference_data,'A',(Line('hold'),),seed=123)
    assert actual[0].seed==expected[0].seed
    assert actual[0].projections[0].hp==expected[0].projections[0].hp


def test_public_line_does_not_reequip_returned_capacity_item_on_a_new_purchase():
    from tft_engine import simulate_lines, Line
    data=capacity_data();item=Entity('capacity_item','item','Capacity item',values={'component':tag(False),'trait_grants':tag({})})
    rules=dict(data.value('team_capacity'))|{'inventory_item_slots':{'capacity_item':{'slots':1,'activation':'continuous','scope':'equipped_anywhere'}}}
    data=replace(data,entities=dict(data.entities)|{item.id:item},static=dict(data.static)|{'team_capacity':tag(rules),
        'rules_flags':tag(dict(data.value('rules_flags'))|{'item_slots_max':3})})
    board=Board((Unit('a'),),(Unit('d',items=('capacity_item',)),))
    data=replace(data,static=dict(data.static)|{'round_types':tag({round_id:'combat' for round_id in data.value('round_order')}),
        'xp_table':tag({str(level):100000 for level in range(1,10)})})
    state=snapshot('2-3',board=board,bench=board.bench,level=1,gold=0,item_bench=(),item_inventory_complete=True,
        shop=({'unit_id':'d','slot':0,'cost':0},))
    lines=(Line('roll',rolls={'2-3':0},stabilize=True),)
    actual=simulate_lines(state,GameHistory(),data,'A',lines,seed=123)[0]
    owned_rules=dict(rules)|{'inventory_item_slots':{'capacity_item':{'slots':1,'activation':'continuous','scope':'owned'}}}
    owned=replace(data,static=dict(data.static)|{'team_capacity':tag(owned_rules)})
    reference=simulate_lines(state,GameHistory(),owned,'A',lines,seed=123)[0]
    assert actual.projections[0].hp<reference.projections[0].hp


@pytest.mark.parametrize('value',[None,True,-1,1.5,float('nan')])
def test_public_advice_pauses_without_a_valid_sourced_slot_certificate(value):
    data=capacity_data();entities=dict(data.entities)
    values=dict(entities['a'].values)
    if value is None:
        values.pop('team_slot_cost')
    else:
        values['team_slot_cost']=tag(value)
    entities['a']=replace(entities['a'],values=values)
    result=evaluate(snapshot(),GameHistory(),replace(data,entities=entities),'review')
    assert result.recommended_board is None and not result.comp_fits and not result.line_results
    assert any(a.payload.get('paused') for a in result.advice)


def test_public_capacity_observation_conflict_and_staleness_pause_instead_of_adding_slots():
    from datetime import timedelta
    data=capacity_data();state=snapshot(team_slot_budget=6)
    conflict=evaluate(state,GameHistory(),data,'review')
    assert not conflict.line_results and any('conflicts' in str(a.payload.get('reason')) for a in conflict.advice)
    stale=replace(state,fields=dict(state.fields)|{'team_slot_budget':replace(state.fields['team_slot_budget'],value=5,read_at=state.captured_at-timedelta(seconds=3))})
    unavailable=evaluate(stale,GameHistory(),data,'review')
    assert not unavailable.line_results and any('stale' in str(a.payload.get('reason')) for a in unavailable.advice)


def test_public_power_rejects_conflicting_costs_in_one_shared_unit_pool():
    data=capacity_data();form=Entity('form','unit_form','Synthetic form',1,('fire',),values={
        'team_slot_cost':tag(2),'pool_id':tag('a'),'canonical_id':tag('a')})
    with pytest.raises(DataError,match='shared-pool team slot cost'):
        estimate_strength(Board((Unit('form'),)),3,replace(data,entities=dict(data.entities)|{form.id:form}))


def test_public_inference_requires_observed_budget_when_external_modifiers_are_possible():
    data=capacity_data();item=Entity('capacity_item','item','Capacity item')
    rules=dict(data.value('team_capacity'))|{'inventory_item_slots':{'capacity_item':{'slots':1,'activation':'continuous','scope':'owned'}}}
    data=replace(data,entities=dict(data.entities)|{item.id:item},static=dict(data.static)|{'team_capacity':tag(rules)})
    unavailable=infer_opponent(TraitSighting('opponent','2-3',1,{'fire':1}),data)
    assert not unavailable.probabilities and unavailable.certainty==0
    assert 'observed team slot budget' in unavailable.fallback_reason
    observed=infer_opponent(TraitSighting('opponent','2-3',1,{'fire':1},team_slot_budget=1),data)
    assert observed.probabilities and observed.probabilities.get('c',0)==0


def test_public_hook_capacity_choice_reuses_seed_but_not_the_old_inventory_simulation():
    from tft_engine import Advice, best_choice_fit
    from tft_engine.registry import DomainHook
    data=capacity_data();rules=dict(data.value('team_capacity'))|{'held_augment_slots':{'capacity':{'slots':1,'activation':'held'}}}
    data=replace(data,entities=dict(data.entities)|{'capacity':Entity('capacity','augment','Synthetic capacity')},
        static=dict(data.static)|{'team_capacity':tag(rules),
            'round_types':tag({round_id:'combat' for round_id in data.value('round_order')}),
            'xp_table':tag({str(level):100000 for level in range(1,10)})})
    board=Board((Unit('a'),),(Unit('b'),))
    state=snapshot('2-3',board=board,bench=board.bench,level=1,gold=0,hp=10,comp_lock='A',
        pinned_line={'id':'hold','levels':{},'rolls':{}},held_augments=(),held_augments_complete=True)
    def choice(context):
        before_score,before=best_choice_fit(context,{},hooks=())
        after_score,after=best_choice_fit(context,{'held_augments':('capacity',)},hooks=())
        before_line=next(row for row in before.line_results['A'] if row.line.id=='hold')
        after_line=next(row for row in after.line_results['A'] if row.line.id=='hold')
        return (Advice('capacity_probe','Counterfactual capacity','information',1,'declared_fixture',
            payload={'before_hp':before_line.projections[0].hp,'after_hp':after_line.projections[0].hp,
                'before_seed':before_line.seed,'after_seed':after_line.seed,'before_score':before_score,'after_score':after_score}),)
    original=state.to_dict()
    first=evaluate(state,GameHistory(),data,'review',hooks=(DomainHook('capacity_probe',(),advice=choice),),seed=123)
    option=next(row for row in first.advice if row.decision=='capacity_probe')
    assert option.payload['after_hp']>option.payload['before_hp']
    assert option.payload['before_seed']==option.payload['after_seed']==123
    assert state.to_dict()==original
    assert first==evaluate(state,GameHistory(),data,'review',hooks=(DomainHook('capacity_probe',(),advice=choice),),seed=123)


def test_public_trait_capacity_rejects_boolean_unit_grants_instead_of_counting_them():
    data=capacity_data();rules=dict(data.value('team_capacity'))|{'trait_bonuses':({'trait_id':'fire','breakpoint':2,'slots':1,'activation':'continuous'},)}
    data=replace(data,static=dict(data.static)|{'team_capacity':tag(rules),'trait_rules':tag({'a':{'counts':{'fire':True}}})})
    with pytest.raises(DataError,match='trait grant'):
        estimate_strength(Board((Unit('a'),Unit('d'))),1,data)


def test_direct_public_lines_reject_conflicting_observed_capacity_before_scoring():
    from tft_engine import simulate_lines, Line
    with pytest.raises(DataError,match='Observed team slot budget conflicts'):
        simulate_lines(snapshot(team_slot_budget=6),GameHistory(),capacity_data(),'A',(Line('hold'),))


@pytest.mark.parametrize('data_factory',[patch,capacity_data])
def test_public_lines_resolve_stage_tolerance_in_both_slot_models(data_factory):
    from tft_engine import simulate_lines, Line
    data=data_factory();state=snapshot('2-3',gold=0)
    expected=simulate_lines(state,GameHistory(),data,'A',(Line('hold'),),seed=123)
    staged=replace(data,tunables=dict(data.tunables)|{'transition_tolerance':tag({str(stage):.02 for stage in range(1,9)})})
    assert simulate_lines(state,GameHistory(),staged,'A',(Line('hold'),),seed=123)==expected


def test_public_selection_does_not_treat_a_bench_slot_as_an_occupied_board_hex():
    owned=Board((Unit('a',position=0),),(Unit('d',position=0),))
    state=snapshot('2-3',board=owned,bench=owned.bench,level=2,gold=0)
    result=evaluate(state,GameHistory(),capacity_data(),'review')
    assert result.recommended_board is not None
    assert {unit.unit_id for unit in result.recommended_board.units}=={'a','d'}
    assert next(unit for unit in result.recommended_board.units if unit.unit_id=='d').position is None
    step=next(a for a in result.advice if a.option_id=='transition').payload['steps'][0]
    assert step['in_index']==1 and step['operation']=='deploy'


@pytest.mark.parametrize('points',[None,2,'2',(True,2),(1.5,2)])
def test_public_capacity_pauses_on_malformed_trait_breakpoint_certificates(points):
    data=capacity_data();entities=dict(data.entities)
    entities['fire']=replace(entities['fire'],values=dict(entities['fire'].values)|{'breakpoints':tag(points)})
    rules=dict(data.value('team_capacity'))|{'trait_bonuses':({'trait_id':'fire','breakpoint':2,'slots':1,'activation':'continuous'},)}
    result=evaluate(snapshot(),GameHistory(),replace(data,entities=entities,static=dict(data.static)|{'team_capacity':tag(rules)}),'review')
    assert result.recommended_board is None and not result.line_results
    assert any('trait support' in str(a.payload.get('reason','')) for a in result.advice)


def test_public_power_rejects_boolean_observed_trait_capacity_counts():
    data=capacity_data();rules=dict(data.value('team_capacity'))|{'trait_bonuses':({'trait_id':'fire','breakpoint':2,'slots':1,'activation':'continuous'},)}
    data=replace(data,static=dict(data.static)|{'team_capacity':tag(rules)})
    with pytest.raises(DataError,match='observed capacity trait count'):
        estimate_strength(Board((Unit('a'),),trait_counts={'fire':True}),1,data)


def test_direct_public_line_target_form_cannot_certify_an_owned_variable_base():
    from tft_engine import simulate_lines, Line
    data=capacity_data();entities=dict(data.entities)
    entities['a_fire']=Entity('a_fire','unit_form','Synthetic fire form',1,('fire',),values={
        'team_slot_cost':tag(1),'pool_id':tag('a'),'canonical_id':tag('a')})
    rules={'a':{'replace':({'fire':1},{})},'a_fire':{'counts':{'fire':1}}}
    guides=dict(data.guides);guides['A']=replace(guides['A'],units=('a_fire','b'),carry_ids=('a_fire',))
    data=replace(data,entities=entities,guides=guides,static=dict(data.static)|{'trait_rules':tag(rules)})
    owned=Board((Unit('a'),),trait_counts={'fire':1})
    state=snapshot(board=owned,bench=(),gold=0)
    with pytest.raises(DataError,match='resolved own trait form'):
        simulate_lines(state,GameHistory(),data,'A',(Line('hold'),),seed=123)
    resolved=Board((Unit('a_fire'),),trait_counts={'fire':1})
    positive=snapshot(board=resolved,bench=(),gold=0)
    assert simulate_lines(positive,GameHistory(),data,'A',(Line('hold'),),seed=123)
    assert owned.units[0].unit_id=='a'
