"""Decision advice at the approved Engine boundary with synthetic source tables."""
from dataclasses import replace
from .test_planning import patch, snapshot, tag
from tft_engine import Board, Unit, GameHistory, evaluate
from tft_data.models import Entity


def item_patch():
    data=patch(); entities=dict(data.entities)
    for id,role in (('a','AD'),('b','tank'),('c','AP'),('d','tank')):
        entities[id]=replace(entities[id],values=dict(entities[id].values)|{'item_class':tag(role),'item_reference':tag(0)})
    entities.update({id:Entity(id,'item',id,values={'category':tag(category),'item_class':tag(role),'component':tag(category=='component')})
        for id,category,role in (('sword','component','AD'),('rod','component','AP'),('ADitem','finished','AD'),('APitem','finished','AP'),('remover','tool','utility'),('reforger','tool','utility'))})
    guides={id:replace(guide,items={guide.carry_ids[0]:('ADitem' if id=='A' else 'APitem',)}) for id,guide in data.guides.items()}
    static=dict(data.static)|{'rules_flags':tag(dict(data.value('rules_flags'))|{'item_slots_max':3,'wisp_purchase_shop_slots_delta':1}),
        'item_recipes':tag({'ADitem':('sword','sword'),'APitem':('rod','rod')})}
    tunables=dict(data.tunables)|{'item_class_prior':tag({'AD':{'AD':.5,'AP':0,'utility':.1},'AP':{'AD':0,'AP':.5,'utility':.1},'tank':{'AD':0,'AP':0,'utility':.1}}),
        'item_prior_strength':tag(100),'component_income_by_stage':tag({str(s):{'sword':0,'rod':0} for s in range(1,9)}),
        'component_discount_by_stage':tag({str(s):1 for s in range(1,9)}),'slam_candidate_cap':tag(3),'open_candidate_temperature':tag(1),
        'board_power_buy_min':tag(.1)}
    return replace(data,entities=entities,guides=guides,static=static,tunables=tunables)


def test_shop_buys_target_key_and_pair_analytically_but_respects_hold_allowance():
    data=patch()
    data=replace(data,tunables=dict(data.tunables)|{'board_power_buy_min':tag(0.1)})
    owned=Board((Unit('a'),),(Unit('b'),))
    state=snapshot(board=owned,bench=owned.bench,level=1,gold=30,comp_lock='A',
        pinned_line={'id':'hold','levels':{},'rolls':{}},shop=(
            {'slot':0,'unit_id':'a','cost':1},{'slot':1,'unit_id':'b','cost':1},
            {'slot':2,'unit_id':'d','cost':3}))
    report=evaluate(state,GameHistory(),data,'review')
    shop=next(a for a in report.advice if a.decision=='shop')
    assert shop.payload['buys']==({'slot':0,'unit_id':'a','cost':1.0,'reason':'target_key'},)
    assert {o.payload['slot'] for o in shop.options if o.action=='buy'}=={0,1,2}
    assert next(o for o in shop.options if o.action=='buy' and o.payload['slot']==1).payload['eligible_reason']=='pair'
    assert next(o for o in shop.options if o.action=='buy' and o.payload['slot']==1).payload['allowed'] is False
    assert all(o.expected_placement is None for o in shop.options)
    assert shop.payload['cost_units']=='gold'
    assert report==evaluate(state,GameHistory(),data,'review')


def test_item_fit_assigns_current_pairs_exactly_and_keeps_wrong_class_items_out_of_fit():
    data=item_patch()
    state=snapshot('2-3',board=Board((Unit('a'),)),bench=(),item_bench=('sword','sword','rod'),item_inventory_complete=True)
    report=evaluate(state,GameHistory(),data,'review')
    assert report.comp_fits['A'].terms['item'].delta==-.5
    assert report.comp_fits['B'].terms['item'].delta==0
    assert report.comp_fits['A'].terms['item'].numbers['assignment']==(('ADitem','a'),)
    unknown=replace(state,fields={k:v for k,v in state.fields.items() if k!='item_bench'})
    absent=evaluate(unknown,GameHistory(),data,'review')
    assert all('item' not in f.terms for f in absent.comp_fits.values())
    assert not any(a.decision=='item' for a in absent.advice)


def test_slam_prices_generic_tempo_plus_exact_item_fit_with_a_same_seed_pair():
    data=item_patch()
    state=snapshot('2-3',board=Board((Unit('a'),)),bench=(),level=1,gold=0,item_bench=('sword','sword'),item_inventory_complete=True,comp_lock='A')
    report=evaluate(state,GameHistory(),data,'review')
    slam=next(a for a in report.advice if a.decision=='item' and a.payload.get('operation')=='build')
    assert slam.payload['item_id']=='ADitem' and slam.payload['holder']=='a'
    assert slam.payload['consume_components']==('sword','sword')
    assert slam.numbers['placement_gain']>0
    assert slam.numbers['item_fit_gain']==0 # The held pair already has exact assignment value.
    assert slam.options and slam.options[0].standard_error is not None
    assert slam.options[0].payload['cost_units']=='placement'
    assert report==evaluate(state,GameHistory(),data,'review')


def test_wisp_prices_sourced_gold_effect_and_cost_and_requires_positive_round_count():
    data=item_patch()
    data=replace(data,static=dict(data.static)|{'wisps':tag({'gold_wisp':{'effect_kind':'gold','values':{'gold':8},'cost':1,'offer_stages':('3',)}}),
        'wisp_round_cap':tag({'default':1,'trait_overrides':{}})},tunables=dict(data.tunables)|{'wisp_buy_margin':tag(.0001)})
    state=snapshot(gold=30,slot_count=4,wisp={'wisp_id':'gold_wisp','cost':1,'slot':4},wisp_complete=True,
        wisp_purchases_this_round=0,wisp_purchase_count_complete=True,item_bench=(),item_inventory_complete=True)
    report=evaluate(state,GameHistory(),data,'review')
    wisp=next(a for a in report.advice if a.decision=='wisp')
    assert wisp.payload['operation']=='buy' and wisp.payload['cost']==1
    assert wisp.payload['cost_units']=='gold' and wisp.numbers['placement_gain']>0
    assert wisp.options[0].standard_error is not None
    assert wisp.options[0].payload['before']['seed']==wisp.options[0].payload['after']['seed']
    unknown=replace(state,fields={k:v for k,v in state.fields.items() if k!='wisp_purchases_this_round'})
    assert not any(a.decision=='wisp' and a.urgency!='information' for a in evaluate(unknown,GameHistory(),data,'review').advice)


def test_augment_tiers_value_each_offer_and_reroll_nonbest_available_options():
    data=item_patch()
    data=replace(data,augment_tiers={'Sbuff':'S','Abuff':'A','Bbuff':'B','other':'S'},
        comp_augment_tiers={'A':{'Sbuff':'S'}},static=dict(data.static)|{'econ_augments':tag({}),
            'augment_pools':tag({'silver':('Sbuff','Abuff','Bbuff','other'),'gold':(),'prismatic':()})},
        tunables=dict(data.tunables)|{'augment_tier_delta':tag({'S':-.3,'A':-.15,'B':0,'C':.15,'D':.3,'silver':0,'gold':0,'prismatic':0}),
            'augment_prior_strength':tag(100),'augment_flag_prior_multiplier':tag(2)})
    state=snapshot(phase='augment',planning_phase=False,item_bench=(),item_inventory_complete=True,held_augments=(),held_augments_complete=True,
        augments=({'slot':0,'augment_id':'Sbuff','reroll_available':True},
            {'slot':1,'augment_id':'Abuff','reroll_available':True},{'slot':2,'augment_id':'Bbuff','reroll_available':False}),
        augment_offers_complete=True,augment_tier='silver')
    report=evaluate(state,GameHistory((snapshot('3-1',comp_lock='A'),)),data,'review')
    pick=next(a for a in report.advice if a.decision=='augment' and a.payload['operation']=='pick')
    assert pick.payload['augment_id']=='Sbuff'
    assert {'shop','slot_count','roll_down','remaining_effects','remaining_effects_complete'}<=set(pick.validity_state['fields'])
    assert len(pick.options)>=4 and all(o.expected_placement is not None for o in pick.options)
    assert pick.options[-1].action=='defer'
    assert pick.confidence<data.tunable('confidence_high_min')
    reroll=next(a for a in report.advice if a.decision=='augment' and a.payload['operation']=='reroll')
    assert reroll.payload['slots']==(1,)
    assert report.plan.planning_round=='3-1' and not report.comp_fits


def test_carousel_scores_each_remaining_option_and_reranks_without_observed_plan_mutation():
    data=item_patch()
    state=snapshot('2-4',phase='carousel',planning_phase=False,item_bench=(),item_inventory_complete=True,
        carousel_complete=True,carousel=({'slot':0,'unit_id':'a','item_id':'ADitem'},
            {'slot':1,'unit_id':'c','item_id':'APitem'}))
    history=GameHistory((snapshot('2-3',comp_lock='A'),))
    report=evaluate(state,history,data,'review')
    choice=next(a for a in report.advice if a.decision=='carousel')
    assert choice.payload['ranking'][0]==choice.option_id
    assert len(choice.options)==3 # Two choices and explicit leave/hold baseline.
    assert all(o.standard_error is not None for o in choice.options)
    assert report.plan.planning_round=='2-3' and not report.comp_fits
    vanished=replace(state,fields=dict(state.fields)|{'carousel':replace(state.fields['carousel'],value=(state.field('carousel')[1],))})
    remaining=next(a for a in evaluate(vanished,history,data,'review').advice if a.decision=='carousel')
    assert remaining.payload['ranking']==('carousel:1:c:APitem',)
    assert state.field('item_bench')==() and len(state.field('carousel'))==2


def test_decision_fingerprints_cover_required_inputs_and_buy_margin_uses_stage_map():
    data=replace(item_patch(),tunables=dict(item_patch().tunables)|{'board_power_buy_min':tag({'3':999})})
    state=snapshot(comp_lock='A',shop=({'slot':0,'unit_id':'d','cost':3},),item_bench=(),item_inventory_complete=True)
    report=evaluate(state,GameHistory(),data,'review')
    shop=next(a for a in report.advice if a.decision=='shop' and not a.payload.get('paused'))
    assert not shop.payload['buys']
    assert {'shop','board','bench','gold','inventory_complete','phase','planning_phase'}<=set(shop.validity)
    assert shop.validity_state['fields']['gold']['value']==state.field('gold')
    assert shop.validity_state['data_snapshot_id']==data.snapshot_id


def test_positioning_uses_global_assignment_and_never_produces_placement_scores():
    from datetime import timedelta
    data=item_patch()
    weights_a=(.9,.8)+(.001,)*26
    weights_b=(.89,.01)+(.001,)*26
    data=replace(data,guides={id:replace(g,positions={}) for id,g in data.guides.items()},positioning={'a':weights_a,'b':weights_b})
    board=Board((Unit('a',position=5),Unit('b')))
    state=snapshot(board=board,bench=(),level=2,comp_lock='A',board_settled_since=(snapshot().captured_at-timedelta(seconds=3)).isoformat())
    data=replace(data,tunables=dict(data.tunables)|{'board_settle_seconds':tag(2),'threat_share_on':tag(.5),'threat_share_off':tag(.3)})
    layout=next(a for a in evaluate(state,GameHistory(),data,'review').advice if a.decision=='positioning')
    assert layout.payload['layout']==({'unit_index':0,'unit_id':'a','cell':1},{'unit_index':1,'unit_id':'b','cell':0})
    assert layout.payload['arrows']==({'unit_index':0,'from':5,'to':1},)
    assert layout.placement_impact==0 and not layout.options
    assert not any(a.decision=='positioning' and a.urgency!='information' for a in evaluate(replace(state,fields={k:v for k,v in state.fields.items() if k!='board_settled_since'}),GameHistory(),data,'review').advice)


def test_positioning_trait_threat_hysteresis_protects_owner_cells_and_ignores_unscouted_players():
    from datetime import timedelta
    from tft_engine import TraitSighting, FieldValue
    data=item_patch(); entities=dict(data.entities)
    entities['fire']=replace(entities['fire'],threat_tags=('backline_access',))
    data=replace(data,entities=entities,guides={id:replace(g,positions={'a':27,'b':20}) for id,g in data.guides.items()},
        static=dict(data.static)|{'rules_flags':tag(dict(data.value('rules_flags'))|{'recent_opponent_exclusion_count':0}),'positioning_templates':tag({'anti_dive':{'carry_cells':(21,27),'bodyguard_cells':{'21':(14,), '27':(20,)}}})},
        tunables=dict(data.tunables)|{'board_settle_seconds':tag(2),'threat_share_on':tag(.5),'threat_share_off':tag(.3)})
    board=Board((Unit('a',position=27),Unit('b',position=20)))
    old=snapshot('3-1',board=board,bench=(),level=2,comp_lock='A',board_settled_since=(snapshot().captured_at-timedelta(seconds=13)).isoformat())
    old=replace(old,captured_at=old.captured_at-timedelta(seconds=10),fields={k:replace(v,read_at=v.read_at-timedelta(seconds=10)) for k,v in old.fields.items()})
    seen=(TraitSighting('p1','3-1',2,{'fire':2}),TraitSighting('p2','3-1',2,{}))
    first=next(a for a in evaluate(old,GameHistory(sightings=seen),data,'review').advice if a.decision=='positioning')
    assert first.payload['threat_shares']['backline_access']==.5 and first.payload['voice'] is True
    assert first.payload['layout'][0]['cell']==21 and first.payload['layout'][1]['cell']==14
    state=snapshot(board=board,bench=(),level=2,comp_lock='A',lobby={'p1':60,'p2':60,'p3':60,'unscouted':60},board_settled_since=(snapshot().captured_at-timedelta(seconds=3)).isoformat())
    history=GameHistory((old,),seen+(TraitSighting('p3','3-2',2,{}),))
    next_layout=next(a for a in evaluate(state,history,data,'review').advice if a.decision=='positioning')
    assert next_layout.payload['threat_shares']['backline_access']==1/3
    assert next_layout.payload['adjustments']['backline_access'] is True
    locked=replace(state,fields=dict(state.fields)|{'position_locks':FieldValue({'a':27},state.captured_at,'owner')})
    protected=next(a for a in evaluate(locked,history,data,'review').advice if a.decision=='positioning')
    assert protected.payload['layout'][0]['cell']==27
    away=replace(state,fields=dict(state.fields)|{'recent_opponent_fights_complete':FieldValue(True,state.captured_at,'fixture'),'recent_opponent_fights':FieldValue(({'opponent_id':'p1','round_id':'3-1','read_at':old.captured_at.isoformat()},),old.captured_at,'fixture')})
    excluded=replace(data,static=dict(data.static)|{'rules_flags':tag(dict(data.value('rules_flags'))|{'recent_opponent_exclusion_count':1})})
    off=next(a for a in evaluate(away,history,excluded,'review').advice if a.decision=='positioning' and a.payload.get('operation')=='layout')
    assert off.payload['adjustments']['backline_access'] is False


def test_item_places_finished_items_and_uses_remover_for_a_staying_wrong_class_holder():
    data=item_patch(); entities=dict(data.entities)
    for id in ('remover','reforger'):
        entities[id]=replace(entities[id],values=dict(entities[id].values)|{'tool_kind':tag(id)})
    data=replace(data,entities=entities)
    board=Board((Unit('a'),Unit('b',items=('ADitem',))))
    state=snapshot('3-2',board=board,bench=(),level=2,gold=0,comp_lock='A',item_bench=('remover',),item_inventory_complete=True)
    report=evaluate(state,GameHistory(),data,'review')
    move=next(a for a in report.advice if a.decision=='item' and a.payload.get('operation')=='remove_and_transfer')
    assert move.payload['from']=='b' and move.payload['holder']=='a'
    assert move.payload['consume_tool']=='remover' and move.payload['item_ids']==('ADitem',)
    assert move.payload['realized_holder_gain']==.5
    assert move.options[0].payload['after_item_state']['units'][0]['items']==('ADitem',)
    without=replace(state,fields=dict(state.fields)|{'item_bench':replace(state.fields['item_bench'],value=())})
    assert not any(a.payload.get('operation')=='remove_and_transfer' for a in evaluate(without,GameHistory(),data,'review').advice)


def test_item_choices_use_same_seed_best_comp_fit_and_complete_offer_evidence():
    data=item_patch()
    state=snapshot('3-2',phase='augment',planning_phase=False,choice_kind='item',item_bench=(),item_inventory_complete=True,
        item_offers=({'slot':0,'item_id':'ADitem'},{'slot':1,'item_id':'APitem'}),item_offers_complete=True)
    choice=next(a for a in evaluate(state,GameHistory((snapshot('3-1',comp_lock='A'),)),data,'review').advice if a.decision=='item' and a.payload.get('operation')=='pick')
    assert choice.payload['item_id']=='ADitem'
    assert len(choice.options)==3 and all(o.standard_error is not None for o in choice.options)
    assert choice.options[0].payload['before']['seed']==choice.options[0].payload['after']['seed']


def test_wisp_random_unit_and_item_grants_retain_source_weights_and_paired_option_evidence():
    data=item_patch()
    data=replace(data,static=dict(data.static)|{'wisps':tag({'grant':{'effect_kind':'unit_grant','values':{'outcomes':(
        {'probability':.75,'unit_ids':('a',)}, {'probability':.25,'unit_ids':('c',)})},'cost':0,'offer_stages':('3',)}}),
        'wisp_round_cap':tag({'default':1,'trait_overrides':{}})},tunables=dict(data.tunables)|{'wisp_buy_margin':tag(0)})
    state=snapshot(comp_lock='A',gold=30,slot_count=4,wisp={'wisp_id':'grant','cost':0,'slot':4},wisp_complete=True,
        wisp_purchases_this_round=0,wisp_purchase_count_complete=True,item_bench=(),item_inventory_complete=True)
    advice=next(a for a in evaluate(state,GameHistory(),data,'review').advice if a.decision=='wisp')
    assert advice.payload.get('paused') is not True
    assert len(advice.options)==2 and advice.options[-1].action=='skip'
    assert tuple(row['probability'] for row in advice.options[0].payload['outcomes'])==(.75,.25)
    assert all(row['before']['seed']==row['after']['seed'] for row in advice.options[0].payload['outcomes'])
    assert advice.options[0].standard_error is not None


def test_captured_econ_effect_counts_price_only_remaining_rewards_and_never_repeat_initial_gold():
    from tft_engine import DomainHook
    data=item_patch()
    data=replace(data,static=dict(data.static)|{'econ_augments':tag({'income':{'effect_kind':'gold','values':{'gold':10,'gold_per_round':2,'duration_rounds':5}}})})
    state=snapshot('3-7',gold=30,pinned_line={'id':'hold','levels':{},'rolls':{}},held_augments=('income',),held_augments_complete=True,
        remaining_effects=({'effect_id':'income','source_kind':'augment','remaining_rounds':1},),remaining_effects_complete=True)
    report=evaluate(state,GameHistory(),data,'review',hooks=())
    line=next(r for r in report.line_results['A'] if r.line.id=='hold')
    assert line.projections[0].gold==41 # 39 ordinary income +2 remaining reward, no +10 initial reward.
    baseline=replace(state,fields=dict(state.fields)|{'held_augments':replace(state.fields['held_augments'],value=()),'remaining_effects':replace(state.fields['remaining_effects'],value=())})
    control=next(r for r in evaluate(baseline,GameHistory(),data,'review',hooks=()).line_results['A'] if r.line.id=='hold')
    assert line.projections[1].gold-control.projections[1].gold==3 # +2 retained gold and +1 interest, no second reward.
    unknown=replace(state,fields={k:v for k,v in state.fields.items() if k!='remaining_effects'})
    paused=evaluate(unknown,GameHistory(),data,'review',hooks=())
    assert not paused.line_results and any(a.payload.get('paused') for a in paused.advice)


def test_reforger_requires_wrong_class_and_sourced_outcomes_without_double_counting_fit_gain():
    data=item_patch(); entities=dict(data.entities)
    entities['reforger']=replace(entities['reforger'],values=dict(entities['reforger'].values)|{'tool_kind':tag('reforger')})
    data=replace(data,entities=entities,static=dict(data.static)|{'reforge_pools':tag({'APitem':({'probability':1.0,'item_id':'ADitem'},)})})
    board=Board((Unit('a',items=('APitem',)),Unit('b')))
    state=snapshot(board=board,bench=(),level=2,comp_lock='A',item_bench=('reforger',),item_inventory_complete=True)
    reforge=next(a for a in evaluate(state,GameHistory(),data,'review').advice if a.decision=='item' and a.payload.get('operation')=='reforge')
    assert reforge.payload['consume_tool']=='reforger'
    assert reforge.payload['item_fit_gain']==.5 and reforge.payload['realized_holder_gain']==0
    assert reforge.payload['outcomes'][0]['item_id']=='ADitem'
    correct=replace(state,fields=dict(state.fields)|{'board':replace(state.fields['board'],value=Board((Unit('a',items=('ADitem',)),Unit('b'))))})
    assert not any(o.action=='reforge' for a in evaluate(correct,GameHistory(),data,'review').advice for o in a.options)


def test_augment_statistics_prefer_canonical_pick_stage_and_flagged_prior_confidence():
    from tft_data.models import Statistic
    data=item_patch(); entities=dict(data.entities)
    entities['buff']=Entity('buff','augment','Buff',values={'global_baseline_placement':tag(4),'statistics_min_samples':tag(500),'augment_tier':tag('silver')})
    rows=(Statistic('buff','augment',3,1000,'test','fixture',pick_stage=1),Statistic('buff','augment',5,1000,'test','fixture',pick_stage=2,changed=True))
    data=replace(data,entities=entities,statistics=data.statistics+rows,augment_tiers={'buff':'B'},
        static=dict(data.static)|{'econ_augments':tag({}),'augment_pick_rounds':tag({'2-1':1,'3-2':2,'4-2':3})},
        tunables=dict(data.tunables)|{'augment_tier_delta':tag({'B':0,'silver':0}),'augment_prior_strength':tag(100),'augment_flag_prior_multiplier':tag(2)})
    def held(round):
        return snapshot(round,held_augments=('buff',),held_augments_complete=True,item_bench=(),item_inventory_complete=True)
    early=evaluate(held('2-1'),GameHistory(),data,'review').comp_fits['A'].terms['augment']
    later=evaluate(held('3-2'),GameHistory(),data,'review').comp_fits['A'].terms['augment']
    fallback=evaluate(held('4-2'),GameHistory(),data,'review').comp_fits['A'].terms['augment']
    assert abs(early.delta+1000/1100)<1e-12
    assert abs(later.delta-1000/1200)<1e-12 and later.confidence<=data.tunable('confidence_medium_min')
    assert fallback.delta==0 and fallback.numbers['sources'][0][1]=='thin_statistics_global_tier'


def test_direct_line_and_unchanged_choice_projection_share_remaining_effects_once():
    from tft_engine import Advice, DomainHook, best_choice_fit, simulate_lines, Line
    data=item_patch()
    data=replace(data,static=dict(data.static)|{'econ_augments':tag({'income':{'effect_kind':'gold','values':{'gold':10,'gold_per_round':2,'duration_rounds':5}}})})
    state=snapshot('3-7',gold=30,pinned_line={'id':'hold','levels':{},'rolls':{}},held_augments=('income',),held_augments_complete=True,
        remaining_effects=({'effect_id':'income','source_kind':'augment','remaining_rounds':1},),remaining_effects_complete=True)
    def proof(context):
        score,result=best_choice_fit(context,{},hooks=())
        row=next(r for r in result.line_results['A'] if r.line.id=='hold')
        return (Advice('proof','Same projection','information',1,'same_seed',payload={'gold':row.projections[0].gold,'seed':row.seed}),)
    report=evaluate(state,GameHistory(),data,'review',hooks=(DomainHook('proof',(),advice=proof),))
    line=next(r for r in report.line_results['A'] if r.line.id=='hold')
    direct=simulate_lines(state,GameHistory(),data,'A',(Line('hold'),),seed=line.seed,backup_id=report.plan.backup)[0]
    unchanged=next(a for a in report.advice if a.decision=='proof')
    assert line==direct and unchanged.payload['gold']==41 and unchanged.payload['seed']==line.seed


def test_repeated_fresh_poll_keeps_semantic_econ_decision_and_random_tape_stable():
    from datetime import timedelta
    data=item_patch(); state=snapshot(item_bench=(),item_inventory_complete=True)
    poll=replace(state,snapshot_id='next-poll',captured_at=state.captured_at+timedelta(milliseconds=250),
        fields={key:replace(value,read_at=value.read_at+timedelta(milliseconds=250)) for key,value in state.fields.items()})
    first=next(a for a in evaluate(state,GameHistory(),data,'review').advice if a.decision=='econ')
    later=next(a for a in evaluate(poll,GameHistory(),data,'review').advice if a.decision=='econ')
    assert first.decision_id==later.decision_id and first.option_id==later.option_id
    assert first.options==later.options
    assert first.validity_state['fields']['gold']['read_at']!=later.validity_state['fields']['gold']['read_at']


def test_polymorph_highest_star_is_deterministic_and_barter_modifies_actual_roll_sales():
    data=item_patch(); entities=dict(data.entities)
    entities['a']=replace(entities['a'],cost=3)
    entities['b']=replace(entities['b'],cost=2)
    entities['e']=Entity('e','unit','E',2,('fire',),values={'play_rate':tag(.5),'item_class':tag('AD'),'item_reference':tag(0)})
    entities['f']=Entity('f','unit','F',1,('fire',),values={'play_rate':tag(.5),'item_class':tag('tank'),'item_reference':tag(0)})
    effects={'morph':{'effect_kind':'polymorph','values':{'eligible_costs':(2,),'target':'highest_star','cost_delta':1,
        'preserve_stars':True,'preserve_items':True,'outcomes':{'3':({'probability':1.0,'unit_id':'a'},)}},'cost':0,'offer_stages':('3',)},
        'barter':{'effect_kind':'sale_modifier','values':{'sale_gold_by_cost_star':{'3':{'2':8}},'scope':'rest_of_game'},'cost':0,'offer_stages':('3',)}}
    data=replace(data,entities=entities,static=dict(data.static)|{'wisps':tag(effects),'wisp_round_cap':tag({'default':1,'trait_overrides':{}})},tunables=dict(data.tunables)|{'wisp_buy_margin':tag(0)})
    board=Board((Unit('a'),Unit('b',2)),(Unit('e'),Unit('d',2)))
    state=snapshot(board=board,bench=board.bench,level=2,comp_lock='A',slot_count=4,wisp={'wisp_id':'morph','cost':0,'slot':4},
        wisp_complete=True,wisp_purchases_this_round=0,wisp_purchase_count_complete=True,item_bench=(),item_inventory_complete=True)
    morph=next(a for a in evaluate(state,GameHistory(),data,'review').advice if a.decision=='wisp')
    assert morph.payload.get('paused') is not True
    assert len(morph.options[0].payload['outcomes'])==1
    outcome=morph.options[0].payload['outcomes'][0]['outcome']
    assert outcome=={'target_index':1,'from':'b','to':'a','stars':2}
    barter=replace(state,fields=dict(state.fields)|{'wisp':replace(state.fields['wisp'],value={'wisp_id':'barter','cost':0,'slot':4}),
        'pinned_line':replace(state.fields['gold'],value={'id':'roll','levels':{},'rolls':{'3-2':50}})})
    sale=next(a for a in evaluate(barter,GameHistory(),data,'review').advice if a.decision=='wisp')
    assert sale.payload.get('paused') is not True
    before_roll=next(row for row in sale.payload['before_lines']['A'] if row['line']['id']=='roll')
    after_roll=next(row for row in sale.payload['after_lines']['A'] if row['line']['id']=='roll')
    assert after_roll['projections'][0]['gold']>before_roll['projections'][0]['gold']


def test_risky_wisp_pays_price_in_every_sourced_conditional_simulation():
    data=item_patch()
    data=replace(data,static=dict(data.static)|{'wisps':tag({'risk':{'effect_kind':'risky','values':{'outcomes':(
        {'probability':.5,'effect':{'effect_kind':'gold','values':{'gold':8}}},
        {'probability':.5,'effect':{'effect_kind':'gold','values':{'gold':0}}})}}}),
        'wisp_round_cap':tag({'default':1,'trait_overrides':{}})},tunables=dict(data.tunables)|{'wisp_buy_margin':tag(0)})
    state=snapshot(gold=30,pinned_line={'id':'hold','levels':{},'rolls':{}},comp_lock='A',
        slot_count=4,wisp={'wisp_id':'risk','cost':2,'slot':4},wisp_complete=True,
        wisp_purchases_this_round=0,wisp_purchase_count_complete=True,item_bench=(),item_inventory_complete=True)
    report=evaluate(state,GameHistory(),data,'review')
    advice=next(a for a in report.advice if a.decision=='wisp' and a.options)
    outcomes=advice.options[0].payload['outcomes']
    assert tuple(row['after']['projections'][0]['gold'] for row in outcomes)==(45,36)
    assert 'gold_pair' not in advice.options[0].payload
    assert all(row['before']['seed']==row['after']['seed'] for row in outcomes)
    assert advice.options[0].standard_error is not None


def test_remover_offer_values_realized_handover_without_double_counting_abstract_assignment():
    data=item_patch(); entities=dict(data.entities)
    entities['remover']=replace(entities['remover'],values=dict(entities['remover'].values)|{'tool_kind':tag('remover')})
    data=replace(data,entities=entities)
    state=snapshot('2-3',board=Board((Unit('a'),Unit('c',items=('ADitem',)))),bench=(),level=2,gold=0,
        item_bench=(),item_inventory_complete=True,comp_lock='A',choice_kind='item',item_offers_complete=True,
        item_offers=({'slot':0,'item_id':'remover'},{'slot':1,'item_id':'rod'}))
    result=evaluate(state,GameHistory(),data,'review')
    choice=next(a for a in result.advice if a.decision=='item' and a.payload.get('operation')=='pick')
    assert choice.payload['item_id']=='remover'
    assert choice.payload['placement_gain']==.5
    assert choice.options[0].payload['after_lines']==choice.options[0].payload['before_lines']
    assert choice.options[0].payload['after_plan']['target']=='A'
    assert state.field('item_bench')==() and state.field('board').units[1].items==('ADitem',)


def test_request_local_simulation_reuse_preserves_all_advice_and_conditional_variance():
    data=item_patch()
    data=replace(data,augment_tiers={'x':'S','y':'A','z':'B','new':'S'},
        static=dict(data.static)|{'econ_augments':tag({}),'augment_pools':tag({'silver':('x','y','z','new')})},
        tunables=dict(data.tunables)|{'augment_tier_delta':tag({'S':-.3,'A':-.15,'B':0,'silver':0}),
            'augment_prior_strength':tag(100),'augment_flag_prior_multiplier':tag(2)})
    state=snapshot(phase='augment',planning_phase=False,item_bench=('sword',),item_inventory_complete=True,
        held_augments=(),held_augments_complete=True,augment_tier='silver',augment_offers_complete=True,
        augments=tuple({'slot':slot,'augment_id':id,'reroll_available':True} for slot,id in enumerate(('x','y','z'))))
    history=GameHistory((snapshot('3-1',hp=20,comp_lock='A'),))
    cached=evaluate(state,history,data,'review')
    ordinary=evaluate(state,history,data,'review',reuse_simulations=False)
    assert tuple(a.to_dict() for a in cached.advice)==tuple(a.to_dict() for a in ordinary.advice)
    assert cached.plan==ordinary.plan and cached.comp_fits==ordinary.comp_fits and cached.line_results==ordinary.line_results
    assert cached==evaluate(state,history,data,'review')
    choices=next(a for a in cached.advice if a.decision=='augment' and a.payload['operation']=='pick')
    assert choices.options[0].payload['after']['rollout_placements']==ordinary.advice[next(i for i,a in enumerate(ordinary.advice) if a.decision=='augment' and a.payload['operation']=='pick')].options[0].payload['after']['rollout_placements']


def test_positioning_unknown_matchup_policy_keeps_base_layout_but_pauses_adjustments():
    data=item_patch(); data=replace(data,positioning={'a':tuple(1 if i==0 else 0 for i in range(28))},
        tunables=dict(data.tunables)|{'board_settle_seconds':tag(2),'threat_share_on':tag(.5),'threat_share_off':tag(.3)})
    state=snapshot(board=Board((Unit('a',position=1),)),bench=(),level=1,gold=0,comp_lock='A',
        board_settled_since='2026-01-01T00:00:00+00:00')
    result=evaluate(state,GameHistory(),data,'review')
    base=next(a for a in result.advice if a.decision=='positioning' and a.payload.get('operation')=='layout')
    assert base.payload['layout'][0]['cell']==0
    assert base.payload['threats_available'] is False and base.payload['voice'] is False
    assert any(a.decision=='positioning' and a.payload.get('paused') for a in result.advice)


def test_augment_reroll_reports_keep_and_all_scored_outcomes_with_paired_error_even_when_kept():
    data=item_patch()
    data=replace(data,augment_tiers={'x':'S','y':'B','z':'B','new':'D'},
        static=dict(data.static)|{'econ_augments':tag({}),'augment_pools':tag({'silver':('x','y','z','new')})},
        tunables=dict(data.tunables)|{'augment_tier_delta':tag({'S':-.3,'B':0,'D':.3,'silver':0}),
            'augment_prior_strength':tag(100),'augment_flag_prior_multiplier':tag(2)})
    state=snapshot(phase='augment',planning_phase=False,item_bench=(),item_inventory_complete=True,
        held_augments=(),held_augments_complete=True,augment_tier='silver',augment_offers_complete=True,
        augments=tuple({'slot':slot,'augment_id':id,'reroll_available':slot==0} for slot,id in enumerate(('x','y','z'))))
    result=evaluate(state,GameHistory((snapshot('3-1',comp_lock='A'),)),data,'review')
    pick=next(a for a in result.advice if a.decision=='augment' and a.payload['operation']=='pick')
    assert not any(a.payload.get('operation')=='reroll' for a in result.advice)
    choices={o.option_id:o for o in pick.options}
    assert {'augment:keep','augment:reroll:0','augment:pool:new'}<=set(choices)
    assert choices['augment:reroll:0'].expected_placement>choices['augment:keep'].expected_placement
    assert choices['augment:reroll:0'].standard_error is not None
    assert choices['augment:reroll:0'].payload['baseline_option_id']=='augment:keep'
    assert choices['augment:pool:new'].payload['probability']==1


def test_offline_wisp_worth_uses_explicit_standard_states_and_unmodelled_live_offers_stay_static():
    from tft_engine import compute_wisp_worth
    data=item_patch()
    data=replace(data,static=dict(data.static)|{'wisps':tag({'gold':{'effect_kind':'gold','values':{'gold':8},'cost':1,'offer_stages':('3',)},
        'unknown':{'effect_kind':'unmodelled','values':{},'cost':0,'offer_stages':('3',)}}),
        'wisp_round_cap':tag({'default':1,'trait_overrides':{}}),'wisp_worth_overrides':tag({'unknown':{'3':'situational'}})},
        tunables=dict(data.tunables)|{'wisp_buy_margin':tag(0)})
    standard=snapshot(gold=30,slot_count=4,comp_lock='A',item_bench=(),item_inventory_complete=True)
    table=compute_wisp_worth(data,{'3':standard})
    assert table['gold']['3']['label']=='worth_it' and table['gold']['3']['placement_gain']>0
    assert table['unknown']['3']['label']=='situational' and table['unknown']['3']['source']=='owner'
    live=replace(data,static=dict(data.static)|{'wisp_worth_table':tag(table)})
    state=snapshot(slot_count=4,wisp={'wisp_id':'unknown','slot':4,'cost':0},wisp_complete=True,
        wisp_purchases_this_round=0,wisp_purchase_count_complete=True,item_bench=(),item_inventory_complete=True)
    advice=tuple(a for a in evaluate(state,GameHistory(),live,'review').advice if a.decision=='wisp')
    assert advice and all(a.urgency=='information' for a in advice)
    assert any(a.payload.get('label')=='situational' and a.payload.get('model_unavailable') for a in advice)
    assert table==compute_wisp_worth(data,{'3':standard})


def test_remaining_effect_counter_cannot_turn_a_gold_source_into_unobserved_free_rolls():
    data=item_patch(); data=replace(data,static=dict(data.static)|{'econ_augments':tag({'gold':{'effect_kind':'gold','values':{'gold':8}}})})
    state=snapshot(held_augments=('gold',),held_augments_complete=True,remaining_effects_complete=True,
        remaining_effects=({'effect_id':'gold','source_kind':'augment','remaining_rolls':2},))
    result=evaluate(state,GameHistory(),data,'review')
    assert not result.comp_fits and not result.line_results
    assert any(a.decision=='econ' and a.payload.get('paused') and 'counter' in a.payload['reason'].lower() for a in result.advice)


def test_roll_discount_expires_after_its_sourced_round_count():
    from tft_engine import Line, simulate_lines
    from tft_engine.lines import SimulationEffects
    data=item_patch()
    guide=replace(data.guides['A'],units=('a',),carry_ids=('a',),line=({'round':'3-7','level':1,'target_stars':{'a':3}},))
    rules=dict(data.value('rules_flags')); entities={id:data.entities[id] for id in ('a','fire')}
    rounds=data.value('round_order')
    data=replace(data,entities=entities,guides={'A':guide},static=dict(data.static)|{
        'round_types':tag({r:'pve' for r in rounds}),'rules_flags':tag(rules|{'pve_orb_gold':{}}),
        'econ_augments':tag({'discount':{'effect_kind':'rolls','values':{'roll_cost_delta':-1,'duration_rounds':1}}})})
    state=snapshot('3-7',board=Board((Unit('a'),)),bench=(),level=1,gold=4,slot_count=1,streak=-3,
        held_augments=('discount',),held_augments_complete=True,remaining_effects_complete=True,
        remaining_effects=({'effect_id':'discount','source_kind':'augment','remaining_rounds':1},))
    line=Line('roll',{}, {r:0 for r in rounds if r>='3-7'})
    bounded=simulate_lines(state,GameHistory(),data,'A',(line,),seed=1)[0]
    plain=replace(state,fields={k:v for k,v in state.fields.items() if k not in ('held_augments','held_augments_complete','remaining_effects','remaining_effects_complete')})
    permanent=simulate_lines(plain,GameHistory(),data,'A',(line,),effects=SimulationEffects(roll_cost_delta=-1),seed=1)[0]
    assert next(p for p in bounded.projections if p.round_id=='4-2').hit_probability==0
    assert next(p for p in permanent.projections if p.round_id=='4-2').hit_probability==1
    assert bounded.projections[0].gold==permanent.projections[0].gold==6


def test_shop_reports_explicit_hold_and_sells_lowest_priority_overflow_before_second_buy():
    data=item_patch(); data=replace(data,static=dict(data.static)|{'bench_size':tag(1)})
    board=Board((Unit('a'),),(Unit('d'),))
    state=snapshot(board=board,bench=board.bench,level=1,gold=30,comp_lock='A',
        pinned_line={'id':'hold','levels':{},'rolls':{}},shop=({'slot':0,'unit_id':'a','cost':1},))
    shop=next(a for a in evaluate(state,GameHistory(),data,'review').advice if a.decision=='shop')
    assert any(o.option_id=='shop:hold' and o.action=='hold' for o in shop.options)
    buy=next(o for o in shop.options if o.action=='buy')
    assert buy.payload['overflow_sells']==('d',) and buy.payload['overflow_gold']==3
    assert buy.payload['after_bench']==({'unit_id':'a','stars':1,'items':(),'position':None},)
    assert shop.payload['buys'][0]['overflow_sells']==('d',)


def test_positioning_remains_available_when_only_economy_fields_are_unread():
    data=item_patch(); data=replace(data,positioning={'a':tuple(1 if i==0 else 0 for i in range(28))},
        static=dict(data.static)|{'rules_flags':tag(dict(data.value('rules_flags'))|{'recent_opponent_exclusion_count':0})},
        tunables=dict(data.tunables)|{'board_settle_seconds':tag(2),'threat_share_on':tag(.5),'threat_share_off':tag(.3)})
    state=snapshot(board=Board((Unit('a',position=1),)),bench=(),level=1,comp_lock='A',board_settled_since='2026-01-01T00:00:00+00:00')
    state=replace(state,fields={k:v for k,v in state.fields.items() if k!='gold'})
    result=evaluate(state,GameHistory(),data,'review')
    assert any(a.decision=='econ' and a.payload.get('paused') for a in result.advice)
    assert any(a.decision=='positioning' and a.payload.get('operation')=='layout' for a in result.advice)


def test_wisp_purchase_refills_sourced_champion_slots_without_mutating_observed_shop():
    data=item_patch(); data=replace(data,static=dict(data.static)|{
        'rules_flags':tag(dict(data.value('rules_flags'))|{'wisp_purchase_shop_slots_delta':1}),
        'wisps':tag({'zero':{'effect_kind':'gold','values':{'gold':0},'cost':0,'offer_stages':('3',)}}),
        'wisp_round_cap':tag({'default':1,'trait_overrides':{}})},tunables=dict(data.tunables)|{'wisp_buy_margin':tag(0)})
    state=snapshot(board=Board((Unit('a'),)),bench=(),level=1,gold=30,
        slot_count=4,wisp={'wisp_id':'zero','slot':4,'cost':0},wisp_complete=True,wisp_purchases_this_round=0,wisp_purchase_count_complete=True,
        item_bench=(),item_inventory_complete=True)
    result=evaluate(state,GameHistory(),data,'review')
    choice=next(a for a in result.advice if a.decision=='wisp' and a.options)
    assert choice.options[0].payload['champion_slots_after']==5
    assert state.field('slot_count')==4 and state.field('wisp')['wisp_id']=='zero'
    missing=replace(data,static=dict(data.static)|{'rules_flags':tag({k:v for k,v in data.value('rules_flags').items() if k!='wisp_purchase_shop_slots_delta'})})
    assert not any(a.decision=='wisp' and a.urgency!='information' for a in evaluate(state,GameHistory(),missing,'review').advice)


def test_positioning_gap_certificate_blocks_threats_and_future_history_cannot_repair_it():
    from datetime import timedelta
    from tft_engine import FieldValue, TraitSighting
    data=item_patch(); entities=dict(data.entities)
    entities['fire']=replace(entities['fire'],threat_tags=('backline_access',))
    data=replace(data,entities=entities,guides={id:replace(g,positions={'a':27,'b':20}) for id,g in data.guides.items()},
        static=dict(data.static)|{'rules_flags':tag(dict(data.value('rules_flags'))|{'recent_opponent_exclusion_count':1}),
            'positioning_templates':tag({'anti_dive':{'carry_cells':(21,),'bodyguard_cells':{'21':(14,)}}})},
        tunables=dict(data.tunables)|{'board_settle_seconds':tag(2),'threat_share_on':tag(.5),'threat_share_off':tag(.3)})
    board=Board((Unit('a'),Unit('b')))
    state=snapshot(board=board,bench=(),level=2,comp_lock='A',board_settled_since='2026-01-01T00:00:00+00:00',
        recent_opponent_fights=({'opponent_id':'p2','round_id':'3-1','read_at':'2026-01-01T00:00:00+00:00'},),
        recent_opponent_fights_complete=False)
    history=GameHistory(sightings=(TraitSighting('p1','3-1',2,{'fire':2}),))
    current=evaluate(state,history,data,'review')
    layout=next(a for a in current.advice if a.decision=='positioning' and a.payload.get('operation')=='layout')
    assert layout.payload['threats_available'] is False and layout.payload['voice'] is False
    assert layout.payload['layout'][0]['cell']==27
    future=replace(state,captured_at=state.captured_at+timedelta(seconds=1),fields=dict(state.fields)|{
        'recent_opponent_fights_complete':FieldValue(True,state.captured_at+timedelta(seconds=1),'log_projection')})
    assert current==evaluate(state,replace(history,snapshots=(future,)),data,'review')


def test_own_position_rule_precedes_threat_templates_and_identical_poll_does_not_reissue_layout():
    from datetime import timedelta
    from tft_engine import TraitSighting
    data=item_patch(); entities=dict(data.entities)
    entities['fire']=replace(entities['fire'],threat_tags=('backline_access','aoe'))
    data=replace(data,entities=entities,guides={id:replace(g,positions={'a':27,'b':20}) for id,g in data.guides.items()},
        static=dict(data.static)|{'rules_flags':tag(dict(data.value('rules_flags'))|{'recent_opponent_exclusion_count':0}),
            'positioning_rules':tag(({'trait_id':'fire','breakpoint':2,'unit_ids':('a',),'cells':(7,)},)),
            'positioning_templates':tag({'anti_dive':{'carry_cells':(21,),'bodyguard_cells':{'21':(14,)}},'anti_aoe':{'cells':(21,27)}})},
        tunables=dict(data.tunables)|{'board_settle_seconds':tag(2),'threat_share_on':tag(.5),'threat_share_off':tag(.3)})
    board=Board((Unit('a',position=27),Unit('b',position=20)),trait_counts={'fire':2})
    state=snapshot(board=board,bench=(),level=2,comp_lock='A',board_settled_since='2026-01-01T00:00:00+00:00')
    sightings=(TraitSighting('p1','3-1',2,{'fire':2}),)
    result=evaluate(state,GameHistory(sightings=sightings),data,'review')
    layout=next(a for a in result.advice if a.decision=='positioning' and a.payload.get('operation')=='layout')
    assert layout.payload['layout'][0]['cell']==7
    later=replace(state,captured_at=state.captured_at+timedelta(milliseconds=250),fields={k:replace(v,read_at=v.read_at+timedelta(milliseconds=250)) for k,v in state.fields.items()})
    polled=evaluate(later,GameHistory((state,),sightings),data,'review')
    assert not any(a.decision=='positioning' and a.urgency!='information' for a in polled.advice)


def test_duplicator_uses_one_star_copy_and_invalid_polymorph_preservation_does_not_enable_action():
    data=item_patch(); data=replace(data,static=dict(data.static)|{
        'wisps':tag({'copy':{'effect_kind':'duplicator','values':{'eligible_costs':(1,), 'target':'highest_star','copy_star':'one'}}}),
        'wisp_round_cap':tag({'default':1,'trait_overrides':{}})},tunables=dict(data.tunables)|{'wisp_buy_margin':tag(0)})
    state=snapshot(board=Board((Unit('a',2),)),bench=(),level=1,gold=0,slot_count=4,
        wisp={'wisp_id':'copy','slot':4,'cost':0},wisp_complete=True,wisp_purchases_this_round=0,wisp_purchase_count_complete=True,
        item_bench=(),item_inventory_complete=True)
    copied=next(a for a in evaluate(state,GameHistory(),data,'review').advice if a.decision=='wisp' and a.options)
    assert copied.options[0].payload['outcomes'][0]['outcome']['unit_id']=='a'
    assert copied.options[0].payload['outcomes'][0]['after_fits']['A']['terms']['simulation']['numbers']['hit_probability']==1
    malformed=replace(data,static=dict(data.static)|{'wisps':tag({'copy':{'effect_kind':'polymorph','values':{
        'eligible_costs':(1,),'target':'highest_star','cost_delta':2,'preserve_stars':'False','preserve_items':True,
        'outcomes':{'3':({'unit_id':'c','probability':1},)}}}})})
    assert not any(a.decision=='wisp' and a.urgency!='information' for a in evaluate(state,GameHistory(),malformed,'review').advice)


def test_custom_field_age_policy_is_used_for_reads_after_public_requirement_checks():
    from datetime import timedelta
    data=item_patch(); data=replace(data,tunables=dict(data.tunables)|{'field_max_age_seconds':tag({'default':5,'shop_roll_down':.5})})
    state=snapshot(item_bench=(),item_inventory_complete=True)
    state=replace(state,fields={name:replace(field,read_at=field.read_at-timedelta(seconds=3)) for name,field in state.fields.items()})
    result=evaluate(state,GameHistory(),data,'review')
    assert result.line_results and result.comp_fits
    assert not any(a.decision=='econ' and a.payload.get('paused') for a in result.advice)
    assert result==evaluate(state,GameHistory(),data,'review')
    changed=replace(state,fields=dict(state.fields)|{'gold':replace(state.fields['gold'],value=state.fields['gold'].value+1)})
    after=evaluate(changed,GameHistory(),data,'review')
    assert result.line_results['A'][0].seed!=after.line_results['A'][0].seed


def test_same_seed_option_evidence_has_stable_content_references_for_transport():
    data=item_patch()
    state=snapshot('2-3',board=Board((Unit('a'),)),bench=(),level=1,gold=0,comp_lock='A',item_bench=(),item_inventory_complete=True,choice_kind='item',item_offers_complete=True,item_offers=({'slot':0,'item_id':'ADitem'},{'slot':1,'item_id':'rod'}))
    first=evaluate(state,GameHistory(),data,'review')
    item=next(a for a in first.advice if a.decision=='item' and a.options and a.options[0].payload.get('after_lines'))
    option=item.options[0].payload
    assert option['before_evidence_id'].startswith('sha256:')
    assert option['after_evidence_id'].startswith('sha256:')
    assert option['before_line_ref']['line_id']==option['before']['line']['id']
    assert option['after_line_ref']['seed']==option['after']['seed']
    repeated=evaluate(state,GameHistory(),data,'review')
    repeated_item=next(a for a in repeated.advice if a.option_id==item.option_id and a.decision=='item')
    assert repeated_item.options[0].payload['after_evidence_id']==option['after_evidence_id']
    hold=item.options[-1].payload
    assert hold['before_evidence_id']==hold['after_evidence_id']


def test_remover_offer_unlocks_equipment_on_a_retained_bench_unit_for_a_fielded_holder():
    data=item_patch(); entities=dict(data.entities)
    entities['remover']=replace(entities['remover'],values=dict(entities['remover'].values)|{'tool_kind':tag('remover')})
    data=replace(data,entities=entities)
    board=Board((Unit('a'),),(Unit('b',items=('ADitem',)),))
    state=snapshot('2-3',board=board,bench=board.bench,level=1,gold=0,comp_lock='A',
        item_bench=(),item_inventory_complete=True,choice_kind='item',item_offers_complete=True,
        item_offers=({'slot':0,'item_id':'remover'},{'slot':1,'item_id':'rod'}))
    pick=next(a for a in evaluate(state,GameHistory(),data,'review').advice if a.decision=='item' and a.payload.get('operation')=='pick')
    remover=next(o for o in pick.options if o.payload.get('item_id')=='remover')
    assert remover.payload['placement_gain']==.5
    assert remover.payload['after_fits']['A']['terms']['item']['numbers']['tool_opportunity_gain']==.5
    assert state.field('bench')[0].items==('ADitem',)


def test_reforger_can_replace_wrong_class_equipment_on_an_owned_bench_unit():
    data=item_patch(); entities=dict(data.entities)
    entities['reforger']=replace(entities['reforger'],values=dict(entities['reforger'].values)|{'tool_kind':tag('reforger')})
    data=replace(data,entities=entities,static=dict(data.static)|{'reforge_pools':tag({'ADitem':({'item_id':'APitem','probability':1},)})})
    board=Board((Unit('a'),),(Unit('c',items=('ADitem',)),))
    state=snapshot('2-3',board=board,bench=board.bench,level=1,gold=0,comp_lock='B',item_bench=('reforger',),item_inventory_complete=True)
    advice=next(a for a in evaluate(state,GameHistory(),data,'review').advice if a.decision=='item' and a.options)
    reforge=next(o for o in advice.options if o.action=='reforge')
    assert reforge.payload['holder_index']==1 and reforge.payload['consume_tool']=='reforger'
    assert reforge.payload['item_fit_gain']==.5
    assert state.field('bench')[0].items==('ADitem',)


def test_current_offer_tier_cannot_invent_the_tier_of_an_unknown_held_augment():
    data=item_patch(); data=replace(data,augment_tiers={'x':'S','y':'A','z':'B'},
        static=dict(data.static)|{'econ_augments':tag({}),'augment_pools':tag({'silver':('x','y','z')})},
        tunables=dict(data.tunables)|{'augment_tier_delta':tag({'S':-.3,'A':-.15,'B':0,'silver':0}),'augment_prior_strength':tag(100),'augment_flag_prior_multiplier':tag(2)})
    state=snapshot(phase='augment',planning_phase=False,item_bench=(),item_inventory_complete=True,
        held_augments=('unknown-old-pick',),held_augments_complete=True,augment_tier='silver',augment_offers_complete=True,
        augments=tuple({'slot':i,'augment_id':id,'reroll_available':False} for i,id in enumerate(('x','y','z'))))
    advice=tuple(a for a in evaluate(state,GameHistory(),data,'review').advice if a.decision=='augment')
    assert advice and all(a.urgency=='information' for a in advice)
    assert any(a.payload.get('operation')=='tiers' for a in advice)
