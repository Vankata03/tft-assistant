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
    parser.add_argument('--guides',type=int,default=65)
    parser.add_argument('--rollouts',type=int,default=64)
    parser.add_argument('--state-cap',type=int,default=10000)
    parser.add_argument('--repeats',type=int,default=1)
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('synthetic_engine_examples',Path(__file__).with_name('test_planning.py'))
    fixture=importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
    data=fixture.patch(); tag=fixture.tag
    static=dict(data.static); tunables=dict(data.tunables)
    tunables['rollouts_full']=tag(args.rollouts)
    tunables['opponent_inference_state_cap']=tag(args.state_cap)
    units={f'u{i:02}':Entity(f'u{i:02}','unit',f'Synthetic {i}',i%5+1,('fire',),values={'play_rate':tag(0.5)}) for i in range(65)}
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
    if args.repeats<1:
        parser.error('--repeats must be positive')
    elapsed=[]
    for _ in range(args.repeats):
        start=perf_counter(); result=evaluate(state,fixture.GameHistory(),data,'review'); elapsed.append(perf_counter()-start)
    if any(a.payload.get('paused') for a in result.advice):
        raise RuntimeError([a.to_dict() for a in result.advice])
    if args.result_json:
        args.result_json.write_text(json.dumps({'advice':[a.to_dict() for a in result.advice],'line_results':{id:[r.to_dict() for r in values] for id,values in result.line_results.items()}},sort_keys=True,allow_nan=False))
    output={'qualification':'Mac CPU smoke, synthetic statistics; no Ryzen/live/fitted qualification',
        'guides':len(guides),'roster_units':len(units),'rollouts':args.rollouts,'evaluation_seconds':elapsed,'workload':dict(result.workload),
        'simulated_comps':sum(f.simulated for f in result.comp_fits.values()),'scored_lines':sum(len(v) for v in result.line_results.values())}
    if args.roster_cache:
        from tft_data.adapters import CommunityDragon
        sourced=CommunityDragon(json.loads(args.roster_cache.read_text()),18).entities()
        playable={id:replace(e,values=dict(e.values)|{'play_rate':tag(.5)}) for id,e in sourced.items() if e.kind in ('unit','unit_form','trait')}
        avatar='DA_18_LuxUniqueTrait'
        forms=tuple(e for e in playable.values() if e.kind=='unit_form')
        grants={e.id:{t:1 if t==avatar else 2 for t in e.traits} for e in forms}
        rules={id:{'replace':[counts]} for id,counts in grants.items()}
        rules['DA_Lux18_Base']={'replace':list(grants.values())}
        static=dict(static)|{'trait_rules':tag(rules)}
        actual=replace(data,static=static,entities=playable,guides={},statistics=())
        sighting=TraitSighting('enemy','3-2',8,{avatar:1,'DA_18_Blackthorn':2},2)
        start=perf_counter(); inferred=infer_opponent(sighting,actual); elapsed=perf_counter()-start
        output['sourced_inference']={'roster_units':sum(e.kind=='unit' for e in playable.values()),'forms':len(forms),'seconds':elapsed,'candidate_count':inferred.candidate_count,'certainty':inferred.certainty,'fallback_reason':inferred.fallback_reason,'state_cap':args.state_cap}
    print(json.dumps(output,sort_keys=True))

if __name__=='__main__':
    main()
