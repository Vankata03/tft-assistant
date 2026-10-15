// @vitest-environment jsdom
import {act,createElement} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach,expect,it} from 'vitest'
import {ReviewSection} from '../src/renderer/src/review/ReviewSection'
import {pager} from './fixtures/reviewPager'

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true})

let cleanup:(()=>void)|null=null
afterEach(()=>{cleanup?.();cleanup=null})
async function mount(name:string,document:Record<string,unknown>){
 const host=window.document.createElement('div');window.document.body.append(host)
 const root=createRoot(host)
 cleanup=()=>{act(()=>root.unmount());host.remove()}
 await act(async()=>root.render(createElement(ReviewSection,{name,path:['surface',name],request:pager(document),onDebug:()=>{}})))
 return host
}

it('Game plan timeline shows target, candidates, commit status and pivots as recorded',async()=>{
 const plans=[
  {log_seq:4,round_id:'2-5',status:'open',target:'A',backup:null,candidates:['A','B','C'],called_status:'display_attribution_unavailable',observed_lock:null,pivot_from:null,pivot_to:null,pivot_round:null,rejected_target:null,player_label:'A',divergence_round:null,planning_round:'2-5',target_similarity:.5,evidence_path:['plan_timeline',0]},
  {log_seq:9,round_id:'4-1',status:'committed',target:'B',backup:'A',candidates:['B','A'],called_status:'display_attribution_unavailable',observed_lock:'B',pivot_from:'A',pivot_to:'B',pivot_round:'4-1',rejected_target:'A',player_label:'B',divergence_round:'3-5',planning_round:'4-1',target_similarity:.8,evidence_path:['plan_timeline',1]},
 ]
 const host=await mount('plan_timeline',{surface:{plan_timeline:plans}})
 const text=host.textContent!
 expect(text).toContain('Candidates A, B, C')
 expect(text).toContain('Open · target A')
 expect(text).toContain('Committed · target B · backup A')
 expect(text).toContain('Pivot A → B at 4-1')
 expect(text).toContain('Rejected target A')
 expect(text).toContain('Player comp B · diverged 3-5')
 expect(text).toContain('Called status unavailable · display attribution unavailable')
})

it('fight strip separates the pre-fight forecast from the observed result and keeps missing forecasts explicit',async()=>{
 const fights=[
  {round_id:'3-2',opponent_id:'p4',start_log_seq:21,start_at:'2026-10-14T18:01:02+00:00',result:'loss',actual_hp_loss:9,win_probability:.42,predicted_hp_loss:7.5,confidence:.6,opponent_warning:null,winner_unit_count:5,winner_unit_count_source:'observed',unavailable:{},evidence_path:['fights',0]},
  {round_id:'3-3',opponent_id:'p6',start_log_seq:30,start_at:'2026-10-14T18:03:10+00:00',result:'win',actual_hp_loss:null,win_probability:null,predicted_hp_loss:null,confidence:null,opponent_warning:null,winner_unit_count:null,winner_unit_count_source:null,unavailable:{forecast:'historical_data_or_prefight_context_unavailable'},evidence_path:['fights',1]},
 ]
 const host=await mount('fights',{surface:{fights}})
 const [first,second]=[...host.querySelectorAll('article')].map(node=>node.textContent!)
 expect(first).toContain('Opponent p4 · fight started log 21 · 2026-10-14T18:01:02+00:00')
 expect(first).toContain('Forecast · win 42% · predicted HP loss 7.5')
 expect(first).toContain('Actual · loss · HP lost 9')
 expect(second).toContain('Forecast unavailable · historical data or prefight context unavailable')
 expect(second).toContain('Actual · win · HP lost unavailable')
 expect(second).not.toContain('NaN')
})

it('full timeline shows displayed status, paired uncertainty and the missing capture-gap rows explicitly',async()=>{
 const timeline=[
  {moment_id:'m1',engine_decision_id:'econ:3-2',log_seq:12,round_id:'3-2',category:'econ',cost:-0.42,paired_uncertainty:.11,close_call:false,differed:true,shown:{status:'unavailable',reason:'display_attribution_unavailable'},reason:'line_projection',unavailable:{},evidence_path:['evidence','replay','records',0]},
  {moment_id:'m2',engine_decision_id:'shop:3-2',log_seq:13,round_id:'3-2',category:'shop',cost:null,paired_uncertainty:null,close_call:false,differed:true,shown:{status:'no_advice_in_baseline_mode'},reason:'board_power_gain',unavailable:{paired_uncertainty:'paired_rollouts_unavailable',cost:'domain_does_not_value_placement'},evidence_path:['evidence','replay','records',1]},
 ]
 const host=await mount('timeline',{surface:{timeline}})
 const [first,second]=[...host.querySelectorAll('article')].map(node=>node.textContent!)
 expect(first).toContain('econ · Engine decision econ:3-2 · log 12')
 expect(first).toContain('Estimated signed cost -0.42 ± 0.11')
 expect(first).toContain('Shown status unavailable · display attribution unavailable')
 expect(second).toContain('Differed · no placement cost · domain does not value placement')
 expect(second).toContain('Shown status no advice in baseline mode')
 expect(host.textContent).toContain('Capture gaps are not rows in this section')
})

it('positioning note shows the advised layout and keeps follow attribution unavailable',async()=>{
 const positioning=[{log_seq:18,engine_decision_id:'positioning:3-2',cost:null,reason:'template_layout',action:'Move to target layout',confidence:.5,layout:[{unit_index:0,unit_id:'TFT18_Shen',cell:3},{unit_index:1,unit_id:'TFT18_Jinx',cell:24}],unavailable:{display:'display_attribution_unavailable'},evidence_path:['positioning',0]}]
 const host=await mount('positioning',{surface:{positioning}})
 const text=host.textContent!
 expect(text).toContain('Move to target layout · Engine decision positioning:3-2 · log 18 · confidence 50%')
 expect(text).toContain('TFT18_Shen → hex 3')
 expect(text).toContain('TFT18_Jinx → hex 24')
 expect(text).toContain('Not costed · template layout')
 expect(text).toContain('display unavailable: display_attribution_unavailable')
})

it('Lines show each schedule, risk terms and the pinned schedule without inventing a pinned forecast',async()=>{
 const header=(id:string,levels:Record<string,number>,rolls:Record<string,number>,expected:number)=>({line_id:id,schedule:{id,levels,rolls,stabilize:false,floor_options:[],family_id:null},expected_placement:expected,standard_error:.2,death_probability:.15,hit_probability:.7,confidence:.5,death_placement_cost:.3,projections:[{round_id:'3-3',gold:40,level:6,hp:55,hit_probability:.7,expected_placement:expected,planned_gold:30}]})
 const lines=[{log_seq:7,round_id:'3-2',observed:{gold:35,level:5,hp:60},pin:{id:'roll:now@30',levels:{'3-2':5},rolls:{'3-2':30},stabilize:false,floor_options:[],family_id:'roll:now'},unavailable:{},
  recommended:header('guide:A',{'3-3':6,'4-1':7},{'4-1':20},3.1),actual:header('fitted-hold',{'4-2':7},{},4.2),evidence_path:['lines',0]}]
 const host=await mount('lines',{surface:{lines}})
 const text=host.textContent!
 expect(text).toContain('Levels 3-3 → 6, 4-1 → 7 · roll-downs 4-1 to 20 gold')
 expect(text).toContain('Levels 4-2 → 7 · no roll-down')
 expect(text).toContain('Hit 70% · death 15% · death placement cost 0.30 · confidence 50%')
 expect(text).toContain('Pinned Line roll:now@30 · Levels 3-2 → 5 · roll-downs 3-2 to 30 gold')
 expect(text).toContain('Pinned forecast unavailable · this review records the pinned schedule only')
 expect(host.querySelectorAll('svg').length).toBe(2)
})

it('Lines say when no Line was pinned',async()=>{
 const lines=[{log_seq:7,round_id:'3-2',observed:{gold:35,level:5,hp:60},pin:null,unavailable:{actual_policy:'player_policy_not_identified'},recommended:null,actual:null,evidence_path:['lines',0]}]
 const host=await mount('lines',{surface:{lines}})
 expect(host.textContent).toContain('No Line pinned at this decision')
 expect(host.textContent).toContain('actual policy unavailable: player_policy_not_identified')
 expect(host.textContent).not.toContain('No level-ups')
 expect(host.textContent).not.toContain('Hit unavailable')
})
