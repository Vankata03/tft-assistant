"""Public advice examples using explicitly synthetic patch data."""
from datetime import datetime, timezone, timedelta
from dataclasses import replace
import pytest
from tft_engine import GameSnapshot, GameHistory, FieldValue, Board, Unit
from tft_data.models import DataSnapshot, Entity, Guide, Statistic, TaggedValue

NOW = datetime(2026,10,7,tzinfo=timezone.utc)

def tag(value):
    return TaggedValue(value,'owner')


def test_baseline_and_silent_advice_do_not_require_any_game_or_patch_data():
    from tft_engine import advise
    snapshot=GameSnapshot('g','3-2',NOW)
    assert advise(snapshot,GameHistory(),None,'baseline') == ()
    assert advise(snapshot,GameHistory(),None,'silent') == ()


def test_live_pauses_explicitly_when_required_fields_are_unavailable():
    from tft_engine import advise
    snapshot=GameSnapshot('g','3-2',NOW)
    advice=advise(snapshot,GameHistory(),None,'live')
    assert len(advice)==1
    assert advice[0].decision=='status'
    assert advice[0].urgency=='information'
    assert advice[0].payload['paused'] is True

def patch():
    rounds=tuple(f'{s}-{r}' for s in range(1,7) for r in range(1,8))
    static={
        'round_order':rounds,'round_types':{r:'pve' for r in rounds},
        'xp_table':{'1':2,'2':2,'3':6,'4':10,'5':20,'6':36,'7':56,'8':68,'9':68},
        'gold_by_round':{'default':5},'streak_gold':{'2':1,'5':2,'6':3},
        'interest':{'gold_per_tick':10,'gold_per_interest':1,'cap':5},
        'player_damage':{'stage_base':{str(i):i+1 for i in range(1,9)},'per_survivor':1},
        'rules_flags':{'pve_preserves_streak':True,'passive_xp':2,'xp_buy_cost':4,'xp_buy_amount':4,'roll_cost':2,'unknown_wisp_slots':4.5,'pve_orb_gold':{},'combat_win_gold':1,'champion_slots_max':5},
        'shop_odds':{str(i):[1,0,0,0,0] for i in range(1,11)},'pool_sizes':{str(i):30 for i in range(1,6)},
        'level_calendar':{'1-1':3,'3-1':4,'4-1':5,'5-1':6},
        'stage_items':{str(i):{'finished':0,'component':0,'high_cost_finished':0} for i in range(1,9)},
        'sell_values':{str(i):{'1':i,'2':3*i-1,'3':9*i-1} for i in range(1,6)},
        'trait_rules':{},'lobby_top4_rate':0.5,'bench_size':9,
    }
    tunables={'unit_weight':1,'trait_weight':1,'item_weight':1,'unit_prior_strength':100,'trait_prior_strength':100,
        'cost_star_baseline':{str(c):{'1':c,'2':c+1,'3':c+2} for c in range(1,6)},
        'item_values':{'finished':1,'component':0.35,'high_cost_bonus':0.25},'fight_scale':1,'win_scale_by_stage':{},
        'survivor_scale_by_stage':{str(i):1 for i in range(1,9)},'terminal_hp_weight':1,'terminal_gold_weight':0.001,
        'opponent_star_mix':{'1-1':{str(c):[1,0,0] for c in range(1,6)}},
        'sighting_full_weight_rounds':2,'sighting_half_life_rounds':1,'sighting_persistence_weight':2,
        'emblem_count_prior':{'0':1,'1':0.1,'2':0.01},'emblem_slack_max':2,
        'size_level_prior':{str(l):{str(n):1 for n in range(l+1)} for l in range(1,11)},
        'classifier_weights':{'carry':3,'key':2,'other':1,'bench':0.5},'classifier_threshold':0.5,
        'confidence_medium_min':0.5,'confidence_high_min':0.8,'confidence_show_min':0.2,
        'field_max_age_seconds':{'default':2,'shop_roll_down':0.5},'open_candidate_count':3,'commit_latest_round':'3-2',
        'pivot_margin_by_stage':{'default':0.5,'post_roll_down':0.8},'pivot_reraise_extra':0.2,'transition_tolerance':0.02,
        'rollouts_full':16,'rollouts_reroll':8,'line_candidate_cap':7,'gold_floors':[50,30,10,0],
        'stabilize_rounds_left':3,'all_in_rounds_left':2,'line_margin':0.1,'challengers_simulated':2,
        'default_lines_by_carry_cost':{'1':[{'round':'3-1','level':5,'roll_floor':10}]},'opponent_growth_curve':{},'comp_defining_margin':0.3,
    }
    units={id:Entity(id,'unit',id,cost,('fire',),values={'play_rate':tag(0.5)}) for id,cost in [('a',1),('b',1),('c',3),('d',3)]}
    units['fire']=Entity('fire','trait','Fire',values={'breakpoints':tag([2]),'top4_rate_2':tag(0.5)})
    return DataSnapshot('synthetic','test',18,{k:tag(v) for k,v in static.items()},{k:tag(v) for k,v in tunables.items()},units,
        (Statistic('A','comp',3.9,1000,'test','metatft'),Statistic('B','comp',4.2,1000,'test','metatft')),
        {'A':Guide('A','A',('a','b'),carry_ids=('a',),line=({'round':'3-1','level':5,'roll_floor':10},)),
         'B':Guide('B','A',('c','d'),carry_ids=('c',),line=({'round':'4-2','level':8,'roll_floor':10},))})


def snapshot(round_id='3-2', **changes):
    board=Board((Unit('a',2),),(Unit('c'),))
    values={'board':board,'bench':board.bench,'inventory_complete':True,'phase':'planning','planning_phase':True,'gold':30,'hp':60,'level':5,'xp':0,'streak':-3,'lobby':{'p1':60,'p2':60},'lobby_complete':True,'slot_count':5}
    values.update(changes)
    return GameSnapshot('g',round_id,NOW,{k:FieldValue(v,NOW,'fixture',0.9) for k,v in values.items()},f'g:{round_id}')


def test_advice_has_reproducible_scored_lines_and_pve_preserves_streak_income():
    from tft_engine import advise
    state=snapshot('3-7',pinned_line={'id':'hold','levels':{},'rolls':{}},gold=30)
    first=advise(state,GameHistory(),patch(),'live')
    assert first==advise(GameSnapshot.from_dict(state.to_dict()),GameHistory(),patch(),'review')
    econ=next(a for a in first if a.decision=='econ')
    assert econ.payload['line_id']=='hold'
    projection=econ.payload['projections']['hold']
    # PvE preserves -3 streak: 5 base +3 interest +1 streak, then passive2XP.
    assert projection[0]['gold']==39
    assert projection[0]['hp']==60
    assert projection[0]['level']==5
    assert len(projection)==8 # current3-7 through end of nextstage4-7.
    assert all(option.expected_placement is not None for option in econ.options)

def test_transition_keeps_a_strong_interim_until_the_guides_roll_down_deadline():
    from tft_engine import evaluate
    owned=Board((Unit('c',3),),(Unit('a',2),))
    early=snapshot('2-5',board=owned,bench=owned.bench,level=1,comp_lock='A')
    late=snapshot('3-1',board=owned,bench=owned.bench,level=1,comp_lock='A')
    first=evaluate(early,GameHistory(),patch(),'live')
    second=evaluate(late,GameHistory(),patch(),'live')
    assert first.recommended_board.units[0].unit_id=='c'
    assert second.recommended_board.units[0].unit_id=='a'
    assert next(a for a in second.advice if a.decision=='transition').payload['swap_in']==('a',)


def test_transition_holds_backup_keys_and_sells_bottom_priority_bench_overflow():
    from tft_engine import evaluate
    data=patch()
    data=replace(data,static=dict(data.static)|{'bench_size':tag(1)})
    owned=Board((Unit('a',2),Unit('b')),(Unit('c'),Unit('d')))
    state=snapshot('3-2',board=owned,bench=owned.bench,level=2,comp_lock='A',
        pinned_line={'id':'hold','levels':{},'rolls':{}})
    report=evaluate(state,GameHistory(),data,'review')
    hold=next(a for a in report.advice if a.option_id=='transition:hold')
    sell=next(a for a in report.advice if a.option_id=='transition:sell')
    assert hold.payload['hold']==('c',)
    assert sell.payload['sell']==('d',)
    assert sell.payload['reason']=='bench_overflow'


def test_batched_lines_match_individual_rollouts_with_combat_death_floors_and_effect_pairs():
    from tft_engine import Line, SimulationEffects, simulate_lines, paired_value
    data=patch()
    data=replace(data,static=dict(data.static)|{'round_types':tag({r:'combat' for r in data.static['round_order'].value})})
    owned=Board((Unit('a'),),(Unit('a'),Unit('d')))
    state=snapshot(board=owned,bench=owned.bench,level=1,gold=18,hp=9,streak=-3,
        shop=({'unit_id':'a','cost':1},))
    lines=(Line('hold'),Line('floor10',rolls={'3-2':10}),Line('allin',rolls={'3-2':0}),
        Line('stabilize',rolls={'3-2':0},stabilize=True),Line('level',levels={'3-2':3}))
    effects=SimulationEffects(gold_delta=3,xp_delta=4,free_rolls=2,one_round_power_bonus=2)
    for effect in (None,effects):
        batched=simulate_lines(state,GameHistory(),data,'A',lines,effects=effect,rollouts=32)
        individual=tuple(simulate_lines(state,GameHistory(),data,'A',(line,),effects=effect,rollouts=32)[0] for line in lines)
        assert [r.to_dict() for r in batched]==[r.to_dict() for r in individual]
        assert any(r.death_probability>0 for r in batched)
        assert any(r.standard_error>0 for r in batched)
    gain,error,before,after=paired_value(state,GameHistory(),data,'A',lines,SimulationEffects(),rollouts=32)
    assert gain==error==0
    assert before==after


def test_growth_lookup_reuses_refresh_table_but_recomputation_ignores_old_values():
    from tft_engine import growth_curve, growth_curve_lookup
    data=patch()
    computed=growth_curve(data)
    data=replace(data,tunables=dict(data.tunables)|{'opponent_growth_curve':tag(computed)})
    assert growth_curve_lookup('3-2',data)==computed['3-2']
    changed=replace(data,tunables=dict(data.tunables)|{'unit_weight':tag(2)})
    assert growth_curve_lookup('3-2',changed)==computed['3-2']
    assert growth_curve(changed)['3-2']==2*computed['3-2']


def test_stabilize_finishes_an_interim_pair_outside_target_key_goals():
    from tft_engine import Line, simulate_lines
    data=patch()
    priors={cost:dict(values) for cost,values in data.tunables['cost_star_baseline'].value.items()}
    priors['3']['2']=8
    data=replace(data,tunables=dict(data.tunables)|{'cost_star_baseline':tag(priors)})
    data=replace(data,guides=dict(data.guides)|{'A':replace(data.guides['A'],line=({'round':'4-2','level':2,'roll_floor':10},))})
    owned=Board((Unit('a',2),Unit('c')),(Unit('c'),))
    state=snapshot(board=owned,bench=owned.bench,level=2,gold=13,
        shop=({'unit_id':'c','cost':3},))
    result=simulate_lines(state,GameHistory(),data,'A',(Line('stabilize',rolls={'3-2':10},stabilize=True),),backup_id='B')[0]
    assert result.projections[0].planned_gold==10


@pytest.mark.parametrize('held_item',(False,True))
def test_line_fights_use_swap_improvement_when_greedy_misses_a_trait_breakpoint(held_item):
    from tft_engine import Line, simulate_lines, evaluate, strength, placement, growth_curve_lookup
    data=patch()
    units=dict(data.entities)
    units['a']=replace(units['a'],cost=3,traits=())
    units['c']=replace(units['c'],cost=1)
    units['fire']=replace(units['fire'],values={'breakpoints':tag([2]),'top4_rate_2':tag(.95)})
    units['finished']=Entity('finished','item','Finished',values={'component':tag(False)})
    guide=replace(data.guides['A'],units=('b','c'),carry_ids=('b',),line=({'round':'3-1','level':2},))
    rules=dict(data.static['rules_flags'].value)|{'passive_xp':0}
    data=replace(data,entities=units,guides={'A':guide},static=dict(data.static)|{'rules_flags':tag(rules)},
        tunables=dict(data.tunables)|{'terminal_gold_weight':tag(0)})
    owned=Board((Unit('a'),Unit('b',items=('finished',) if held_item else ())), (Unit('c'),))
    state=snapshot(board=owned,bench=owned.bench,level=2,gold=0)
    recommended=evaluate(state,GameHistory(),data,'review').recommended_board
    assert {u.unit_id for u in recommended.units}=={'b','c'}
    expected=placement(strength(recommended,2,data),(growth_curve_lookup('3-2',data),)*2,60,(60,60),8,data)
    result=simulate_lines(state,GameHistory(),data,'A',(Line('hold'),),rollouts=4)[0]
    assert result.projections[0].expected_placement==pytest.approx(expected)


def test_line_deadline_forces_target_carry_with_the_transition_membership_order():
    from tft_engine import Line, simulate_lines, evaluate, strength, placement, growth_curve_lookup
    data=patch()
    guide=replace(data.guides['A'],units=('a','c'),line=({'round':'3-2','level':1,'roll_floor':10},))
    data=replace(data,guides={'A':guide},static=dict(data.static)|{'rules_flags':tag(dict(data.static['rules_flags'].value)|{'passive_xp':0})},
        tunables=dict(data.tunables)|{'terminal_gold_weight':tag(0)})
    owned=Board((Unit('c'),),(Unit('a'),))
    state=snapshot(board=owned,bench=owned.bench,level=1,gold=0,comp_lock='A')
    recommended=evaluate(state,GameHistory(),data,'review').recommended_board
    assert recommended.units[0].unit_id=='a'
    expected=placement(strength(recommended,1,data),(growth_curve_lookup('3-2',data),)*2,60,(60,60),8,data)
    result=simulate_lines(state,GameHistory(),data,'A',(Line('hold'),),rollouts=4)[0]
    assert result.projections[0].expected_placement==pytest.approx(expected)


def test_fixed_generic_items_and_item_state_pairs_follow_the_line_spec_amendment():
    from tft_engine import Line, SimulationEffects, simulate_lines, paired_value, evaluate, strength, placement, growth_curve_lookup
    data=patch()
    entities=dict(data.entities)|{'finished':Entity('finished','item','Finished',values={'component':tag(False)})}
    guide=replace(data.guides['A'],units=('a',),line=({'round':'3-2','level':1,'roll_floor':10},))
    data=replace(data,entities=entities,guides={'A':guide},static=dict(data.static)|{'rules_flags':tag(dict(data.static['rules_flags'].value)|{'passive_xp':0})},
        tunables=dict(data.tunables)|{'terminal_gold_weight':tag(0)})
    owned=Board((Unit('c',items=('finished',)),),(Unit('a'),))
    state=snapshot(board=owned,bench=owned.bench,level=1,gold=0,comp_lock='A')
    lines=(Line('hold'),Line('roll',rolls={'3-2':10}))
    recommended=evaluate(state,GameHistory(),data,'review').recommended_board
    assert recommended.units[0].unit_id=='a'
    assert recommended.units[0].items==() # No physical item transfer is inferred.
    # The amended Line model keeps its initial generic term across subsets:
    # finished1 + high-cost-holder bonus0.25, independently of item fit.
    expected=placement(strength(recommended,1,data)+1.25,(growth_curve_lookup('3-2',data),)*2,60,(60,60),8,data)
    results=simulate_lines(state,GameHistory(),data,'A',lines,rollouts=16)
    assert all(r.projections[0].expected_placement==pytest.approx(expected) for r in results)
    gain,error,before,after=paired_value(state,GameHistory(),data,'A',lines,SimulationEffects(item_state=owned),rollouts=16)
    assert gain==error==0 and before==after
    unbuilt=Board((Unit('c'),),(Unit('a'),))
    gain,error,before,after=paired_value(snapshot(board=unbuilt,bench=unbuilt.bench,level=1,gold=0),GameHistory(),data,'A',lines,
        SimulationEffects(item_state=owned),rollouts=16)
    assert gain>0 and error>=0
    assert all(left.seed==right.seed for left,right in zip(before,after))


@pytest.mark.parametrize('locked',(False,True))
def test_choice_hook_values_gold_on_the_current_plan_and_original_random_tape_without_recursion(locked):
    from tft_engine import Advice, DomainHook, FitTerm, SimulationEffects, best_choice_fit, evaluate, simulate_lines
    data=patch()
    controls={'comp_lock':'A','pinned_line':{'id':'hold','levels':{},'rolls':{}}} if locked else {}
    previous=snapshot('3-1',**controls)
    state=snapshot('3-2',choice_offers=('gold',),gold=30,**controls)
    inspected=[]
    def choice(context):
        unchanged,baseline=best_choice_fit(context,{},hooks=(hook,))
        score,result=best_choice_fit(context,{'gold':31},hooks=(hook,))
        inspected.append((context,unchanged,baseline,score,result))
        return (Advice('choice','Take gold','act_this_phase',.5,'choice_fit',numbers={'fit':score},payload={'target':result.plan.target}),)
    hook=DomainHook('choice',('gold','choice_offers'),fit=lambda comp,context:FitTerm(0,'synthetic_choice_term'),advice=choice)
    report=evaluate(state,GameHistory((previous,)),data,'review',hooks=(hook,))
    assert len(inspected)==1 # Counterfactual evaluation never calls choice advice.
    context,unchanged,baseline,score,result=inspected[0]
    assert baseline.plan==context.plan
    assert baseline.comp_fits==context.comp_fits
    assert baseline.line_results==context.line_results
    assert unchanged==min(f.score for f in context.comp_fits.values() if f.simulated)
    assert result.plan.target==context.plan.target=='A'
    assert result.plan.backup==context.plan.backup=='B'
    assert result.plan.line==context.plan.line
    changed=replace(state,fields=dict(state.fields)|{'gold':FieldValue(31,NOW,'choice',1)})
    direct=simulate_lines(changed,context.history,context.data,'A',tuple(r.line for r in result.line_results['A']),
        seed=context.seed,backup_id=result.plan.backup)
    assert result.line_results['A']==direct
    effect_pair=simulate_lines(context.snapshot,context.history,context.data,'A',tuple(r.line for r in result.line_results['A']),
        effects=SimulationEffects(gold_delta=1),seed=context.seed,backup_id=result.plan.backup)
    assert direct==effect_pair
    assert all(r.seed==context.seed for values in result.line_results.values() for r in values)
    assert score==min(f.score for f in result.comp_fits.values() if f.simulated)
    assert score!=unchanged
    assert context.snapshot==state and context.snapshot.field('gold')==30
    assert report.plan==context.plan
    if locked:
        assert report.plan.line.id=='hold'
    assert not any(a.decision=='choice' for a in result.advice)
    repeat_score,repeat=best_choice_fit(context,{'gold':31},hooks=(hook,))
    assert repeat_score==score and repeat==result and len(inspected)==1


def test_choice_fit_suppresses_unavailable_simulation_and_missing_hook_fields():
    from tft_engine import Advice, DomainHook, best_choice_fit, evaluate
    data=patch(); inspected=[]
    state=snapshot(choice_offers=('gold',))
    state=replace(state,fields=dict(state.fields)|{'xp':FieldValue(0,NOW-timedelta(seconds=10),'ocr')})
    def choice(context):
        score,result=best_choice_fit(context,{'gold':31},hooks=(hook,))
        inspected.append((score,result))
        return (Advice('choice','Choice paused','information',0,'unavailable',payload={'paused':score is None}),)
    hook=DomainHook('choice',('gold','choice_offers'),advice=choice)
    report=evaluate(state,GameHistory((snapshot('3-1',comp_lock='A'),)),data,'review',hooks=(hook,))
    assert len(inspected)==1
    score,result=inspected[0]
    assert score is None and not result.comp_fits and not result.line_results
    assert result.plan.target=='A'
    assert next(a for a in result.advice if a.decision=='econ').payload['missing']==('xp',)
    assert next(a for a in report.advice if a.decision=='choice').urgency=='information'
    missing=replace(state,fields={k:v for k,v in state.fields.items() if k!='choice_offers'})
    blocked=evaluate(missing,GameHistory(),data,'review',hooks=(hook,))
    assert len(inspected)==1
    assert next(a for a in blocked.advice if a.decision=='choice').payload['missing']==('choice_offers',)

def test_a_roll_line_buys_key_copies_stops_at_the_floor_and_reports_hit_odds():
    from tft_engine import evaluate
    data=patch()
    guide=replace(data.guides['A'],line=({'round':'3-2','level':1,'roll_floor':10},))
    data=replace(data,guides={'A':guide})
    owned=Board((Unit('a'),),(Unit('a'),))
    state=snapshot('3-2',board=owned,bench=owned.bench,gold=13,level=1,slot_count=1,
        pinned_line={'id':'guide:A','levels':{'3-2':1},'rolls':{'3-2':10}})
    report=evaluate(state,GameHistory(),data,'live')
    econ=next(a for a in report.advice if a.decision=='econ')
    current=econ.payload['projections']['guide:A'][0]
    assert 0<current['hit_probability']<1
    assert current['gold']>=10
    assert econ.numbers['analytic_hit'] == pytest.approx(14/29)
    assert econ.action=='Roll to 10 gold'

def test_open_plan_commits_on_a_key_upgrade_then_uses_history_and_a_picker_lock():
    from tft_engine import evaluate, DomainHook, FitTerm
    data=patch()
    early=snapshot('2-1',board=Board((Unit('a'),)),bench=(),level=3,gold=0)
    open_plan=evaluate(early,GameHistory(),data,'live').plan
    assert open_plan.status=='open'
    upgraded=snapshot('2-2',board=Board((Unit('a',2),)),bench=(),level=3,gold=0)
    committed=evaluate(upgraded,GameHistory((early,)),data,'live').plan
    assert committed.status=='committed'
    assert committed.target=='A'
    # A domain term improves B enough to clear the normal placement margin.
    hook=DomainHook('augment',(),fit=lambda comp,context:FitTerm(-4 if comp=='B' and context.snapshot.field('augments') else 0,'augment_fit'))
    lock=snapshot('2-3',comp_lock='A',augments=('buff',))
    report=evaluate(lock,GameHistory((early,upgraded)),data,'live',hooks=(hook,))
    assert report.plan.target=='A'
    assert report.advice[0].decision=='pivot'
    assert report.advice[0].payload['target']=='B'

def test_missing_xp_pauses_econ_but_preserves_valid_domain_advice_and_the_prior_plan():
    from tft_engine import evaluate, DomainHook, Advice
    data=patch()
    previous=snapshot('3-1',comp_lock='A')
    state=snapshot('3-2',shop=('a',))
    fields=dict(state.fields); fields['xp']=FieldValue(0,NOW-timedelta(seconds=10),'ocr')
    state=replace(state,fields=fields)
    hook=DomainHook('shop',('shop','gold','board','bench'),advice=lambda context:(Advice('shop','Buy A','act_this_phase',0.8,'key_copy',payload={'unit_id':'a','plan':context.plan.target}),))
    report=evaluate(state,GameHistory((previous,)),data,'live',hooks=(hook,))
    assert report.plan.target=='A'
    assert next(a for a in report.advice if a.decision=='shop').payload['plan']=='A'
    assert next(a for a in report.advice if a.decision=='econ').payload['missing']==('xp',)


def test_partial_captured_ownership_pauses_scoring_and_dependent_hooks_but_keeps_independent_advice():
    from tft_engine import Advice, DomainHook, best_choice_fit, evaluate
    data=patch()
    previous=snapshot('3-1',comp_lock='A')
    partial=snapshot('3-2',board=Board((Unit('b'),)),bench=(),inventory_complete=False,
        shop=('a',),choice_offers=('gold',))
    # Decode the real capture/log shape: a positively read subset is a typed
    # Board; its fresh False completeness field prevents treating omitted copies as zero.
    partial=GameSnapshot.from_dict(partial.to_dict())
    inspected=[]
    def independent(context):
        score,result=best_choice_fit(context,{'gold':31},hooks=())
        inspected.append((context,score,result))
        return (Advice('offer','Show captured offer','information',.5,'captured_offer',payload={'offers':context.snapshot.field('choice_offers')}),)
    shop=DomainHook('shop',('shop','gold','board','bench'),advice=lambda context:(Advice('shop','Buy A','act_this_phase',.5,'key_copy'),))
    offer=DomainHook('offer',('choice_offers',),advice=independent)
    report=evaluate(partial,GameHistory((previous,)),data,'review',hooks=(shop,offer))
    assert report.plan.target=='A' # Descriptive last-complete plan is preserved.
    assert not report.comp_fits and not report.line_results and report.recommended_board is None
    assert all(a.urgency=='information' for a in report.advice)
    assert next(a for a in report.advice if a.decision=='shop').payload['missing']==('inventory_complete',)
    assert next(a for a in report.advice if a.decision=='offer').payload['offers']==('gold',)
    context,score,result=inspected[0]
    assert score is None and not result.comp_fits and not result.line_results
    assert result.recommended_board is None
    assert context.plan.target=='A' and not context.comp_fits and not context.line_results
    assert context.recommended_board is None


@pytest.mark.parametrize('completeness',('missing','stale','numeric'))
def test_ownership_requires_a_fresh_positive_completeness_field_before_scoring(completeness):
    from tft_engine import Advice, DomainHook, Line, best_choice_fit, evaluate, simulate_lines
    from tft_data.models import DataError
    data=patch(); state=snapshot()
    fields=dict(state.fields)
    if completeness=='missing':
        fields.pop('inventory_complete')
    elif completeness=='stale':
        fields['inventory_complete']=FieldValue(True,NOW-timedelta(seconds=10),'reader')
    else:
        fields['inventory_complete']=FieldValue(1,NOW,'reader')
    state=GameSnapshot.from_dict(replace(state,fields=fields).to_dict())
    inspected=[]
    def show(context):
        # A choice is not evidence that the original partial inventory became complete.
        score,result=best_choice_fit(context,{'gold':31,'inventory_complete':True},hooks=())
        inspected.append((score,result))
        return (Advice('offer','Show offer','information',.5,'offer'),)
    result=evaluate(state,GameHistory(),data,'live',hooks=(DomainHook('offer',(),advice=show),))
    assert result.plan.target is None
    assert not result.comp_fits and not result.line_results and result.recommended_board is None
    assert all(a.urgency=='information' for a in result.advice)
    assert next(a for a in result.advice if a.decision=='transition').payload['missing']==('inventory_complete',)
    assert inspected[0][0] is None and not inspected[0][1].comp_fits
    with pytest.raises(DataError,match='inventory_complete'):
        simulate_lines(state,GameHistory(),data,'A',(Line('hold'),))


def test_incomplete_history_never_contributes_fit_and_complete_read_resumes_advice():
    from tft_engine import DomainHook, FitTerm, evaluate
    data=patch(); seen=[]
    complete=snapshot('3-1',comp_lock='A')
    partial=snapshot('3-2',board=Board((Unit('c',3),)),bench=(),inventory_complete=False)
    resumed=snapshot('3-3',comp_lock='A')
    hook=DomainHook('observer',(),fit=lambda comp,context:seen.append(context.snapshot.round_id) or FitTerm(0,'observed_complete_state'))
    result=evaluate(resumed,GameHistory((complete,partial)),data,'review',hooks=(hook,))
    assert set(seen)=={'3-1','3-3'}
    assert result.plan.target=='A'
    assert result.comp_fits and result.line_results and result.recommended_board is not None
    assert next(a for a in result.advice if a.decision=='econ').urgency=='act_this_phase'
    assert not any(a.payload.get('paused') for a in result.advice)


@pytest.mark.parametrize('evidence',('missing_phase','missing_flag','stale_phase','stale_flag','false','numeric','combat','end','unknown','conflict'))
def test_core_actions_require_fresh_consistent_positive_planning_evidence(evidence):
    from tft_engine import Advice, DomainHook, best_choice_fit, evaluate
    data=patch(); state=snapshot(choice_offers=('gold',))
    fields=dict(state.fields)
    if evidence.startswith('missing'):
        fields.pop('phase' if evidence=='missing_phase' else 'planning_phase')
    elif evidence.startswith('stale'):
        name='phase' if evidence=='stale_phase' else 'planning_phase'
        fields[name]=replace(fields[name],read_at=NOW-timedelta(seconds=10))
    elif evidence=='false':
        fields['planning_phase']=FieldValue(False,NOW,'reader')
    elif evidence=='numeric':
        fields['planning_phase']=FieldValue(1,NOW,'reader')
    elif evidence in ('combat','end','unknown'):
        fields['phase']=FieldValue(evidence,NOW,'reader')
        fields['planning_phase']=FieldValue(False,NOW,'reader')
    else:
        fields['phase']=FieldValue('augment',NOW,'reader') # Conflicts with True flag.
    state=GameSnapshot.from_dict(replace(state,fields=fields).to_dict())
    inspected=[]
    def information(context):
        score,projection=best_choice_fit(context,{'gold':31,'phase':'planning','planning_phase':True},hooks=())
        inspected.append((context,score,projection))
        return (Advice('offer','Captured offer','information',.5,'observed_offer'),)
    hooks=(DomainHook('offer',('choice_offers',),advice=information),
        DomainHook('shop',(),advice=lambda context:(Advice('shop','Buy A','act_this_phase',.8,'key_copy'),)))
    result=evaluate(state,GameHistory((snapshot('3-1',comp_lock='A'),)),data,'review',hooks=hooks)
    assert result.plan.target=='A' and result.plan.planning_round=='3-1'
    assert not result.comp_fits and not result.line_results and result.recommended_board is None
    assert all(a.urgency=='information' for a in result.advice)
    assert next(a for a in result.advice if a.decision=='econ').payload['paused'] is True
    assert next(a for a in result.advice if a.decision=='offer').action=='Captured offer'
    context,score,projection=inspected[0]
    assert context.plan==result.plan and not context.comp_fits and not context.line_results
    assert context.recommended_board is None and score is None
    assert not projection.comp_fits and not projection.line_results


@pytest.mark.parametrize('phase',('augment','carousel'))
def test_known_choices_use_same_seed_hypothetical_planning_without_folding_observed_choices(phase):
    from tft_engine import Advice, DomainHook, FitTerm, best_choice_fit, evaluate
    data=patch(); inspected=[]; fit_observations=[]
    prior=snapshot('3-1',comp_lock='A')
    choice_history=snapshot('3-2',phase='augment',planning_phase=False,fit_buff=True)
    combat_history=snapshot('3-3',phase='combat',planning_phase=False,fit_buff=True)
    unknown_history=replace(snapshot('3-4',fit_buff=True),fields={k:v for k,v in snapshot('3-4',fit_buff=True).fields.items() if k!='phase'})
    state=GameSnapshot.from_dict(snapshot('3-5',phase=phase,planning_phase=False,choice_offers=('gold',)).to_dict())
    history=GameHistory((prior,choice_history,combat_history,unknown_history))
    def fit(comp,context):
        fit_observations.append((context.snapshot.round_id,context.snapshot.field('phase')))
        return FitTerm(-4 if comp=='B' and context.snapshot.field('fit_buff') else 0,'synthetic_buff')
    def choice(context):
        score,result=best_choice_fit(context,{'gold':31},hooks=(hook,))
        inspected.append((context,score,result))
        return (Advice(phase,'Take gold','act_this_phase',.5,'choice_fit',numbers={'fit':score}),)
    hook=DomainHook(phase,('choice_offers',),fit=fit,advice=choice,advice_phases=(phase,))
    shop=DomainHook('shop',(),advice=lambda context:(Advice('shop','Buy A','act_this_phase',.8,'key_copy'),))
    other=DomainHook('other_choice',(),advice=lambda context:(Advice('other_choice','Take other offer','soon',.5,'choice'),),
        advice_phases=('carousel' if phase=='augment' else 'augment',))
    report=evaluate(state,history,data,'review',hooks=(hook,shop,other))
    assert len(inspected)==1
    context,score,result=inspected[0]
    assert score is not None and result.comp_fits and result.line_results
    projected=replace(state,fields=dict(state.fields)|{
        'phase':FieldValue('planning',NOW,'choice',1),'planning_phase':FieldValue(True,NOW,'choice',1),
        'gold':FieldValue(31,NOW,'choice',1)})
    direct=evaluate(projected,history,data,'review',hooks=(replace(hook,advice=None),),seed=context.seed)
    assert result==direct
    assert all(r.seed==context.seed for values in result.line_results.values() for r in values)
    assert best_choice_fit(context,{'gold':31},hooks=(hook,))==(score,result)
    assert len(inspected)==1 # Fit-only projection never recursively emits choice advice.
    assert context.snapshot==state and context.snapshot.field('planning_phase') is False
    assert report.plan==context.plan and report.plan.planning_round=='3-1'
    assert report.plan.target=='A' and not report.comp_fits and not report.line_results
    assert report.recommended_board is None
    assert next(a for a in report.advice if a.decision==phase).urgency=='act_this_phase'
    assert all(a.urgency=='information' for a in report.advice if a.decision!=phase)
    assert set(fit_observations)=={('3-1','planning'),('3-5','planning')}


def test_roll_down_is_positive_planning_and_publishes_current_actions():
    from tft_engine import Advice, DomainHook, evaluate
    state=snapshot(phase='roll_down',planning_phase=True,roll_down=True)
    hook=DomainHook('shop',(),advice=lambda context:(Advice('shop','Buy A','act_this_phase',.8,'key_copy'),))
    result=evaluate(state,GameHistory(),patch(),'live',hooks=(hook,))
    assert result.plan.planning_round=='3-2' and result.comp_fits and result.line_results
    assert result.recommended_board is not None
    assert next(a for a in result.advice if a.decision=='shop').urgency=='act_this_phase'
    assert next(a for a in result.advice if a.decision=='econ').urgency=='act_this_phase'


def test_pin_is_followed_and_mid_roll_upgrades_stop_without_a_new_seed_policy():
    from tft_engine import advise
    state=snapshot('3-2',pinned_line={'id':'roll:pin','levels':{},'rolls':{'3-2':10}},comp_lock='A')
    econ=next(a for a in advise(state,GameHistory(),patch(),'live') if a.decision=='econ')
    assert econ.payload['line_id']=='roll:pin'
    assert econ.action=='Stop rolling, hold' # carry already2-star; no deliberate extra rolling.
    assert econ.payload['pinned'] is True


def test_same_seed_pairs_share_every_shop_and_fight_when_the_effect_is_zero():
    from tft_engine import paired_value, SimulationEffects, Line
    state=snapshot()
    gain,error,before,after=paired_value(state,GameHistory(),patch(),'A',(Line('roll',rolls={'3-2':10}),),SimulationEffects())
    assert gain==0
    assert error==0
    assert before==after


def test_terminal_gold_has_value_only_for_surviving_rollouts_and_scores_remain_bounded():
    from tft_engine import paired_value, SimulationEffects, Line
    state=snapshot('3-7',board=Board((Unit('a',2),Unit('b',2))),bench=())
    data=patch()
    gain,error,before,after=paired_value(state,GameHistory(),data,'A',(Line('hold'),),SimulationEffects(gold_delta=10))
    assert gain>0
    assert error==pytest.approx(0)
    assert all(1<=v<=3 for v in after[0].rollout_placements)
    # No posthumous gold value: a dead player has the same elimination score.
    dead=replace(state,fields=dict(state.fields)|{'hp':FieldValue(0,NOW,'fixture')})
    gain,error,before,after=paired_value(dead,GameHistory(),data,'A',(Line('hold'),),SimulationEffects(gold_delta=10))
    assert gain==0
    assert before[0].expected_placement==3


def test_dead_and_own_lobby_entries_do_not_change_advice_or_rank_bounds():
    from tft_engine import advise
    base=snapshot('3-7',comp_lock='A',pinned_line={'id':'hold','levels':{},'rolls':{}})
    observed=snapshot('3-7',comp_lock='A',pinned_line={'id':'hold','levels':{},'rolls':{}},
        player_id='self',lobby={'self':60,'p1':60,'p2':60,'dead':0})
    first=next(a for a in advise(base,GameHistory(),patch(),'review') if a.decision=='econ')
    second=next(a for a in advise(observed,GameHistory(),patch(),'review') if a.decision=='econ')
    assert second.payload.get('paused') is not True
    assert first.numbers['expected_placement']==second.numbers['expected_placement']
    assert all(1<=option.expected_placement<=3 for option in second.options)


def test_death_rank_uses_captured_opponent_health_and_power_without_gold_credit():
    from tft_engine import simulate_lines, Line, SimulationEffects
    data=patch(); tables=dict(data.static)
    tables['round_types']=tag({r:'combat' for r in data.static['round_order'].value})
    tables['player_damage']=tag({'stage_base':{str(i):1000 for i in range(1,9)},'per_survivor':1})
    data=replace(data,static=tables,guides={'A':replace(data.guides['A'],units=('a',))})
    state=snapshot('3-7',board=Board((Unit('a',2),)),bench=(),hp=1,gold=0,lobby={'p1':1,'p2':100})
    result=simulate_lines(state,GameHistory(),data,'A',(Line('hold'),),rollouts=128)[0]
    assert result.death_probability>0
    assert 1<result.expected_placement<3
    richer=simulate_lines(state,GameHistory(),data,'A',(Line('hold'),),rollouts=128,effects=SimulationEffects(gold_delta=10))[0]
    for before,after in zip(result.rollout_placements,richer.rollout_placements):
        assert before==after


def test_roll_gold_includes_sales_below_backup_priority_and_preserves_backup_keys():
    from tft_engine import simulate_lines, Line
    data=patch()
    data=replace(data,guides=dict(data.guides)|{'A':replace(data.guides['A'],line=({'round':'3-2','level':1,'roll_floor':10},))})
    owned=Board((Unit('a'),),(Unit('a'),Unit('c')))
    state=snapshot('3-2',board=owned,bench=owned.bench,gold=11,level=1,slot_count=1)
    line=(Line('roll',rolls={'3-2':10}),)
    selling=simulate_lines(state,GameHistory(),data,'A',line,backup_id=None,rollouts=128)[0]
    holding=simulate_lines(state,GameHistory(),data,'A',line,backup_id='B',rollouts=128)[0]
    assert selling.projections[0].hit_probability>0
    assert holding.projections[0].hit_probability==0
    assert holding.projections[0].gold==18 # 11 +5 base +1 interest +1 streak.


def test_ignored_pivot_reverts_after_one_phase_and_requires_the_extra_margin_to_return():
    from tft_engine import evaluate, DomainHook, FitTerm
    data=patch()
    initial=snapshot('2-2',board=Board((Unit('a',2),)),bench=(),gold=0)
    pivot=snapshot('2-3',board=Board((Unit('a',2),)),bench=(),gold=0,augments=('buff',))
    hook=DomainHook('augment',(),fit=lambda comp,ctx:FitTerm(-4 if comp=='B' and ctx.snapshot.field('augments') else 0,'augment_fit'))
    called=evaluate(pivot,GameHistory((initial,)),data,'review',hooks=(hook,))
    assert called.plan.target=='B'
    assert called.plan.pivot_to=='B'
    ignored=snapshot('2-4',board=Board((Unit('a',2),)),bench=(),gold=0,augments=('buff',))
    adopted=evaluate(ignored,GameHistory((initial,pivot)),data,'review',hooks=(hook,))
    assert adopted.plan.target=='A'
    assert adopted.plan.rejected_target=='B'
    assert not any(a.decision=='pivot' for a in adopted.advice)


def test_history_hooks_see_only_the_consumed_prefix_and_future_rounds_are_ignored():
    from tft_engine import evaluate, DomainHook, FitTerm
    seen=[]
    hook=DomainHook('inspect',(),fit=lambda comp,ctx:seen.append((ctx.snapshot.round_id,tuple(s.round_id for s in ctx.history.snapshots))) or FitTerm(0,'inspect'))
    early=snapshot('2-1',gold=0); middle=snapshot('2-2',gold=0); future=snapshot('3-1',gold=0)
    evaluate(snapshot('2-3',gold=0),GameHistory((future,middle,early)),patch(),'review',hooks=(hook,))
    assert seen
    assert all(prefix==() for round_id,prefix in seen if round_id=='2-1')
    assert all(prefix==('2-1',) for round_id,prefix in seen if round_id=='2-2')
    assert all('3-1' not in prefix for _,prefix in seen)


def test_eliminated_rollouts_do_not_buy_shops_or_receive_income_or_xp():
    from tft_engine import simulate_lines, Line
    state=snapshot('3-7',board=Board((Unit('a'),)),bench=(),hp=0,gold=30,level=1,xp=0)
    result=simulate_lines(state,GameHistory(),patch(),'A',(Line('hold'),))[0]
    assert all(p.gold==30 for p in result.projections)
    assert all(p.level==1 for p in result.projections)
    assert all(p.hit_probability==0 for p in result.projections)


def test_stabilize_keeps_rolling_for_board_power_after_the_target_carry_is_hit():
    from tft_engine import simulate_lines, Line
    # B is a strong one-star interim, and the already-hit A carry must not stop stabilization.
    data=patch()
    entities=dict(data.entities); entities['b']=replace(entities['b'],values={'play_rate':tag(.5),'top4_rate_1':tag(.99),'sample_count_1':tag(1000)})
    data=replace(data,entities=entities)
    state=snapshot('3-2',board=Board((Unit('a',2),)),bench=(),gold=30,level=2)
    results=simulate_lines(state,GameHistory(),data,'A',(Line('target',rolls={'3-2':10}),Line('stabilize',rolls={'3-2':10},stabilize=True)),rollouts=128)
    assert results[1].projections[0].gold<results[0].projections[0].gold


def test_simulation_inputs_can_price_xp_free_rolls_and_one_round_power_on_the_same_tape():
    from tft_engine import simulate_lines, paired_value, SimulationEffects, Line
    state=snapshot('3-2',board=Board((Unit('a'),)),bench=(Unit('a'),Unit('b')),gold=1,level=1,xp=0)
    lines=(Line('hold'),)
    data=patch()
    more_xp=simulate_lines(state,GameHistory(),data,'A',lines,effects=SimulationEffects(xp_delta=4))[0]
    base=simulate_lines(state,GameHistory(),data,'A',lines)[0]
    assert more_xp.projections[0].level>base.projections[0].level
    free=simulate_lines(state,GameHistory(),data,'A',lines,effects=SimulationEffects(free_rolls=2))[0]
    assert free.projections[0].hit_probability>base.projections[0].hit_probability
    combat=replace(data,static=dict(data.static)|{'round_types':tag({r:'combat' for r in data.static['round_order'].value})})
    # A lethal current round isolates the one-round buff's survival value;
    # a high-HP terminal-gold tie is sensitive to the changed semantic seed.
    lethal=snapshot('3-2',board=Board((Unit('a'),)),bench=(Unit('a'),Unit('b')),gold=1,level=1,xp=0,hp=5)
    gain,error,before,after=paired_value(lethal,GameHistory(),combat,'A',lines,SimulationEffects(one_round_power_bonus=10),rollouts=128)
    assert after[0].projections[0].hp>before[0].projections[0].hp
    assert after[0].projections[0].hp==5
    assert after[0].projections[1].hp<5 # The bonus expires after the current round.
    assert before[0].seed==after[0].seed
    assert error>=0


def test_refresh_default_line_shapes_support_unguided_comps_and_qualify_their_advice():
    from tft_engine import evaluate
    data=patch()
    comp=Entity('cluster','comp','Unguided',values={'units':tag(('a','b')),'carry_ids':tag(('a',))})
    data=replace(data,entities=dict(data.entities)|{'cluster':comp},
        tunables=dict(data.tunables)|{'default_lines_by_carry_cost':tag({'1':{'line':[{'round':'3-2','level':5,'roll_floor':10}]}})})
    state=snapshot(include_unguided=True,comp_lock='cluster')
    report=evaluate(state,GameHistory(),data,'review')
    assert report.plan.target=='cluster'
    assert all(not a.payload.get('paused') for a in report.advice if a.decision!='positioning')
    assert all(a.confidence<=data.tunables['confidence_medium_min'].value for a in report.advice)
    fallback=replace(data,tunables=dict(data.tunables)|{'default_lines_by_carry_cost':tag({'1':{'roll_level':5}})})
    report=evaluate(state,GameHistory(),fallback,'review')
    assert all(not a.payload.get('paused') for a in report.advice if a.decision!='positioning')
    assert any(r.line.id=='guide:cluster' for r in report.line_results['cluster'])


def test_simulated_comp_fit_exposes_hit_and_death_reason_costs_without_adding_them_twice():
    from tft_engine import evaluate
    owned=Board((Unit('a'),),(Unit('a'),))
    report=evaluate(snapshot('3-2',board=owned,bench=owned.bench,gold=0,level=1,comp_lock='A'),GameHistory(),patch(),'review')
    fit=report.comp_fits['A']
    simulation=fit.terms['simulation']
    assert fit.score==simulation.delta
    assert 'owned_progress' not in fit.terms
    assert simulation.numbers['hit_placement_cost']>0
    assert simulation.numbers['death_placement_cost']==0
    assert simulation.numbers['key_arrival_counterfactual']=='keys_at_main_roll_down_without_shop_uncertainty'


def test_current_captured_key_offer_is_bought_without_a_roll_and_key_prices_can_cross_the_floor():
    from tft_engine import simulate_lines, Line
    owned=Board((Unit('a'),),(Unit('a'),))
    state=snapshot('3-2',board=owned,bench=owned.bench,gold=10,level=1,
        shop=({'slot':0,'unit_id':'a','cost':1},))
    result=simulate_lines(state,GameHistory(),patch(),'A',(Line('roll',rolls={'3-2':10}),))[0]
    assert result.projections[0].hit_probability==1
    assert result.projections[0].planned_gold==9
    assert result.projections[0].gold==15 # 9 +5 base +0 interest +1 streak.


def test_new_backup_priority_matches_the_line_roll_gold_and_sale_advice():
    from tft_engine import evaluate
    data=patch()
    data=replace(data,guides=dict(data.guides)|{'A':replace(data.guides['A'],line=({'round':'3-2','level':1,'roll_floor':10},))})
    owned=Board((Unit('a'),),(Unit('a'),Unit('c')))
    state=snapshot('3-2',board=owned,bench=owned.bench,gold=11,level=1,slot_count=1,comp_lock='A',
        pinned_line={'id':'pin','levels':{},'rolls':{'3-2':10}})
    result=evaluate(state,GameHistory(),data,'review')
    assert result.plan.backup=='B'
    econ=next(a for a in result.advice if a.decision=='econ')
    assert econ.payload['sell_before_roll']==()
    assert econ.payload['projections']['pin'][0]['hit_probability']==0


def test_active_forms_preserve_double_trait_grants_and_share_one_shop_pool():
    from tft_engine import evaluate, strength
    data=patch()
    extra={'lux':Entity('lux','unit','Lux',1,('avatar',),values={'play_rate':tag(.5)}),
        'lux_fire':Entity('lux_fire','unit_form','Lux fire',1,('avatar','fire'),values={'pool_id':tag('lux'),'canonical_id':tag('lux')}),
        'lux_ice':Entity('lux_ice','unit_form','Lux ice',1,('avatar','ice'),values={'pool_id':tag('lux'),'canonical_id':tag('lux')}),
        'avatar':Entity('avatar','trait','Avatar',values={'breakpoints':tag([1]),'top4_rate_1':tag(.5)}),
        'ice':Entity('ice','trait','Ice',values={'breakpoints':tag([2]),'top4_rate_2':tag(.5)})}
    rules={'lux':{'replace':[{'avatar':1,'fire':2},{'avatar':1,'ice':2}]}}
    guide=Guide('luxguide','A',('lux_fire','b'),carry_ids=('lux_fire',),line=({'round':'3-1','level':2,'roll_floor':10},))
    data=replace(data,entities=dict(data.entities)|extra,static=dict(data.static)|{'trait_rules':tag(rules)},guides=dict(data.guides)|{'luxguide':guide})
    owned=Board((Unit('lux_fire',2),),(Unit('lux_fire'),))
    state=snapshot(board=owned,bench=owned.bench,level=2,comp_lock='luxguide')
    result=evaluate(state,GameHistory(),data,'review')
    assert all(not a.payload.get('paused') for a in result.advice if a.decision!='positioning')
    assert result.plan.target=='luxguide'
    assert strength(owned,2,data)==strength(Board(owned.units,owned.bench,{'avatar':1,'fire':2}),2,data)
    assert result.recommended_board.units[0].unit_id=='lux_fire'
    assert strength(owned,2,data)>0
