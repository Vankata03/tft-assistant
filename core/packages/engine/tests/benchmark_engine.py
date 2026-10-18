"""Bounded CPU smoke; synthetic statistics do not qualify gameplay or fitted models."""
import argparse
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
from time import perf_counter
from tft_data.models import Entity, Guide, Statistic
from tft_engine import Board, Unit, TraitSighting, evaluate, infer_opponent


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--roster-cache',type=Path)
    parser.add_argument('--result-json',type=Path)
    parser.add_argument('--combat',action='store_true')
    parser.add_argument('--large-unit',action='store_true',help='Declare one two-slot synthetic roster identity')
    parser.add_argument('--guides',type=int,default=65)
    parser.add_argument('--rollouts',type=int,default=64)
    parser.add_argument('--state-cap',type=int,default=10000)
    parser.add_argument('--repeats',type=int,default=1)
    parser.add_argument('--augment-pool',type=int,default=0)
    parser.add_argument('--no-reuse',action='store_true')
    parser.add_argument('--live',action='store_true',help='Time the complete Live advisor, including bounded reuse on repeated identical inputs')
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('synthetic_engine_examples',Path(__file__).with_name('test_planning.py'))
    fixture=importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
    data=fixture.patch(); tag=fixture.tag
    static=dict(data.static); tunables=dict(data.tunables)
    tunables['rollouts_full']=tag(args.rollouts)
    tunables['opponent_inference_state_cap']=tag(args.state_cap)
    units={f'u{i:02}':Entity(f'u{i:02}','unit',f'Synthetic {i}',i%5+1,('fire',),values={'team_slot_cost':tag(1),'play_rate':tag(0.5)}) for i in range(65)}
    if args.large_unit:
        units['u64']=replace(units['u64'],values=dict(units['u64'].values)|{'team_slot_cost':tag(2)})
    entities=units|{'fire':data.entities['fire']}
    ids=tuple(units)
    guides={f'g{i:02}':Guide(f'g{i:02}','A',tuple(ids[(i+j)%65] for j in range(8)),carry_ids=(ids[i%65],),key_ids=(ids[(i+1)%65],),line=({'round':'3-2','level':6,'roll_floor':10},{'round':'4-2','level':8,'roll_floor':10})) for i in range(args.guides)}
    statistics=tuple(Statistic(id,'comp',4+i/100,1000,'benchmark','metatft') for i,id in enumerate(guides))
    static['shop_odds']=tag({str(i):[.25,.25,.25,.15,.10] for i in range(1,11)})
    if args.combat:
        static['round_types']=tag({r:'combat' for r in static['round_order'].value})
    data=replace(data,static=static,tunables=tunables,entities=entities,guides=guides,statistics=statistics)
    from tft_engine import growth_curve
    data=replace(data,tunables=dict(data.tunables)|{'opponent_growth_curve':tag(growth_curve(data))})
    board=Board(tuple(Unit(ids[i],2 if i==0 else 1) for i in range(6)),tuple(Unit(ids[i]) for i in range(6,15)))
    state=fixture.snapshot(board=board,bench=board.bench,level=6,gold=34,hp=40)
    if args.augment_pool:
        if args.augment_pool<3:
            parser.error('--augment-pool must include at least three shown options')
        from tft_engine import FieldValue
        ids_aug=tuple(f'augment{i}' for i in range(args.augment_pool))
        entities={id:replace(entity,values=dict(entity.values)|{'item_class':tag('AD'),'item_reference':tag(0)}) if entity.kind=='unit' else entity for id,entity in entities.items()}
        entities['synthetic_item']=Entity('synthetic_item','item','Synthetic item',values={'category':tag('finished'),'item_class':tag('AD'),'component':tag(False)})
        guides={id:replace(guide,items={guide.carry_ids[0]:('synthetic_item',)}) for id,guide in guides.items()}
        tunables=dict(data.tunables)|{'item_class_prior':tag({'AD':{'AD':.5}}),'item_prior_strength':tag(100),
            'component_income_by_stage':tag({str(i):{} for i in range(1,9)}),'component_discount_by_stage':tag({str(i):0 for i in range(1,9)}),
            'augment_tier_delta':tag({'S':-.3,'A':-.15,'B':0,'silver':0}),'augment_prior_strength':tag(100),'augment_flag_prior_multiplier':tag(2)}
        static=dict(data.static)|{'rules_flags':tag(dict(data.value('rules_flags'))|{'item_slots_max':3}),
            'item_recipes':tag({}),'econ_augments':tag({}),'augment_pools':tag({'silver':ids_aug})}
        data=replace(data,entities=entities,guides=guides,tunables=tunables,static=static,augment_tiers={id:('S','A','B')[i%3] for i,id in enumerate(ids_aug)})
        values={'phase':'augment','planning_phase':False,'comp_lock':'g00','item_bench':(),'item_inventory_complete':True,
            'held_augments':(),'held_augments_complete':True,'augment_tier':'silver','augment_offers_complete':True,
            'augments':tuple({'slot':i,'augment_id':id,'reroll_available':True} for i,id in enumerate(ids_aug[:3]))}
        state=replace(state,fields=dict(state.fields)|{name:FieldValue(value,state.captured_at,'benchmark_fixture',1) for name,value in values.items()})
    if args.repeats<1:
        parser.error('--repeats must be positive')
    elapsed=[]
    if args.live:
        from tft_live.advisor import LiveAdvisor
        advisor=LiveAdvisor()
    for _ in range(args.repeats):
        start=perf_counter()
        if args.live:
            delivery=advisor.evaluate(state,fixture.GameHistory(),data,mode='live')
        else:
            result=evaluate(state,fixture.GameHistory(),data,'review',reuse_simulations=not args.no_reuse)
        elapsed.append(perf_counter()-start)
    if args.live:
        result=evaluate(state,fixture.GameHistory(),data,'review',reuse_simulations=not args.no_reuse)
    if any(a.payload.get('paused') and a.decision in (('augment',) if args.augment_pool else ('econ','plan','transition')) for a in result.advice):
        raise RuntimeError([(a.decision,a.payload.get('reason')) for a in result.advice if a.payload.get('paused')])
    if args.result_json:
        args.result_json.write_text(json.dumps({'advice':[a.to_dict() for a in result.advice],'line_results':{id:[r.to_dict() for r in values] for id,values in result.line_results.items()}},sort_keys=True,allow_nan=False))
    projected=next((a.options[0].payload['after_lines'] for a in result.advice if a.decision=='augment' and a.options and 'after_lines' in a.options[0].payload),{})
    output={'projected_comps':len(projected),'projected_concrete_lines':sum(len(rows) for rows in projected.values()),'qualification':'Mac CPU smoke, synthetic statistics; no Ryzen/live/fitted qualification',
        'two_slot_fixture':args.large_unit,'augment_pool':args.augment_pool,'simulation_reuse':not args.no_reuse,'guides':len(guides),'roster_units':len(units),'rollouts':args.rollouts,'evaluation_seconds':elapsed,'workload':dict(result.workload),'simulation_diagnostics':dict(result.simulation_diagnostics),
        'simulated_comps':sum(f.simulated for f in result.comp_fits.values()),'scored_lines':sum(len(v) for v in result.line_results.values())}
    if args.live:
        from hashlib import sha256
        evidence=delivery.evidence.resolve()
        diagnostics=evidence.pop('simulation_diagnostics')
        output['live_delivery']={'simulation_diagnostics':diagnostics,
            'decision_evidence_sha256':sha256(json.dumps(evidence,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
            'summary_bytes':len(json.dumps(delivery.content,allow_nan=False).encode()),
            'evidence_records':len(delivery.evidence.objects)}
    if args.roster_cache:
        from tft_data.adapters import CommunityDragon
        sourced=CommunityDragon(json.loads(args.roster_cache.read_text()),18).entities()
        playable={id:replace(e,values=dict(e.values)|{'team_slot_cost':tag(2 if id=='DA_18_ElderDragon' else 1),'play_rate':tag(.5)}) for id,e in sourced.items() if e.kind in ('unit','unit_form','trait')}
        avatar='DA_18_LuxUniqueTrait'
        forms=tuple(e for e in playable.values() if e.kind=='unit_form')
        grants={e.id:{t:1 if t==avatar else 2 for t in e.traits} for e in forms}
        rules={id:{'replace':[counts]} for id,counts in grants.items()}
        rules['DA_Lux18_Base']={'replace':list(grants.values())}
        rules['DA_18_ElderDragon']={'counts':{'DA_Riftbeast18':2}}
        static=dict(static)|{'trait_rules':tag(rules)}
        actual=replace(data,static=static,entities=playable,guides={},statistics=())
        sighting=TraitSighting('enemy','3-2',8,{avatar:1,'DA_18_Blackthorn':2},2)
        start=perf_counter(); inferred=infer_opponent(sighting,actual); elapsed=perf_counter()-start
        output['sourced_inference']={'roster_units':sum(e.kind=='unit' for e in playable.values()),'forms':len(forms),'seconds':elapsed,'candidate_count':inferred.candidate_count,'certainty':inferred.certainty,'fallback_reason':inferred.fallback_reason,'state_cap':args.state_cap}
    print(json.dumps(output,sort_keys=True))

if __name__=='__main__':
    main()
