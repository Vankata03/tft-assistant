/** External preload fixture for exercising the actual renderer; never bundled by Electron. */
import type {
  BaselineContent,
  LiveState,
  EntityDisplay,
  GuideDisplay,
  RequestReview,JsonValue,
} from '../../src/shared/messages'
import type { ShellState } from '../../src/shared/state'
import liveRecording from '../fixtures/live.json'
const reviewKeyframe=new URL('../fixtures/review-keyframe.webp',import.meta.url).href
import { canSelectMode } from '../../src/shared/state'

const unit = (id: string, name: string, cost = 3): EntityDisplay => ({
  id,
  name,
  cost,
  icon: '',
})
const carry = unit('carry', 'Fixture carry'),
  tank = unit('tank', 'Fixture tank', 2),
  support = unit('support', 'Fixture support', 1)
const sword = unit('sword', 'Fixture sword', 0),
  bow = unit('bow', 'Fixture bow', 0),
  blade = unit('blade', 'Fixture blade', 0)
const guide: GuideDisplay = {
  id: 'guide-a',
  name: 'Guide A',
  tier: 'S',
  units: [carry, tank, support],
  early_layout: [
    { entity: tank, position: null },
    { entity: support, position: null },
  ],
  final_layout: [
    { entity: carry, position: 23 },
    { entity: tank, position: 2 },
    { entity: support, position: 17 },
  ],
  stage_tips: {
    '3': 'Fixture stage plan · preserve the Guide carry.',
    '4': 'Fixture next-stage plan.',
  },
  stage_plan: [{ round: '3-4', level: 7 }],
  carousel: [sword, bow],
  alternatives: ['guide-b'],
}
const guideB: GuideDisplay = {
  ...guide,
  id: 'guide-b',
  name: 'Guide B',
  tier: 'A',
  alternatives: ['guide-a'],
}
const content: BaselineContent = {
  patch: 'fixture-patch',
  snapshot_id: 'fixture-static-snapshot',
  round_id: '3-2',
  phase: 'planning',
  guides: [guide, guideB],
  selected: null,
  xp_hint: {
    target_level: 7,
    target_round: '3-4',
    buys: 2,
    gold: 8,
    passive_xp: 4,
    text: 'Guide: 7 at 3-4 · 2 XP buys (8 gold) short',
  },
  par: { probability: 0.54, paused: null, uncertain: false },
  shop: [{ slot: 1, entity: carry, in_guide: true }],
  recipes: [
    {
      unit: carry,
      item: blade,
      components: [
        { entity: sword, held: true },
        { entity: bow, held: false },
      ],
    },
  ],
  augments: [
    {
      entity: unit('aug-a', 'Fixture augment A', 0),
      tier: 'S',
      global_tier: 'A',
      in_guide: true,
      offered: true,
      offer_index: 0,
      average_placement: null, sample_count: null, pick_stage: null,
      statistic_source: null, statistic_scope: null, stale: false, changed: false,
    },
    {
      entity: unit('aug-b', 'Fixture augment B', 0),
      tier: 'B',
      global_tier: 'B',
      in_guide: false,
      offered: false,
      offer_index: null,
      average_placement: null, sample_count: null, pick_stage: null,
      statistic_source: null, statistic_scope: null, stale: false, changed: false,
    },
  ],
  wisps: [
    {
      entity: unit('wisp', 'Fixture Wisp', 0),
      worth: 3.5,
      worth_label: null,
      worth_stage: null,
      paired_standard_error: null,
      reference_source: null,
      source: 'owner',
      offered_slot: 4,
    },
  ],
  faced: [{ name: 'Fixture rival', result: 'win' }],
  warnings: ['Synthetic renderer fixture; no production qualification.'],
  anchors: [
    { kind: 'shop', index: 1, x: 0.22, y: 0.83, width: 0.12, height: 0.04 },
    { kind: 'par', index: 0, x: 0.72, y: 0.07, width: 0.2, height: 0.05 },
    { kind: 'wisp', index: 4, x: 0.8, y: 0.83, width: 0.14, height: 0.04 },
  ],
  overlay_bounds: { x: 0, y: 0, width: 1280, height: 800 },
  overlay_allowed: true,
}
let state: ShellState = {
  core: 'running',
  mode: 'baseline',
  gameflow: { clientRunning: true, phase: 'InProgress' },
  availableModes: ['silent', 'baseline'],
  error: null,
  baseline: {
    v: 1,
    type: 'baseline_state',
    mode: 'baseline',
    status: 'Capture OK',
    stale: [],
    content,
    voice: null,
  },
}
let reviewLocked=true
let liveRefresh:ReturnType<typeof setInterval>|null=null
const listeners = new Set<(state: ShellState) => void>()
const shown: { surface: string; id: string; timestamp: string }[] = []
const reports = document.createElement('output')
function publish(): void {
  for (const listener of listeners) listener(structuredClone(state))
}
const reviewOptionPath=['evidence','replay','contexts',0,'evaluation','advice',0,'options'] as (string|number)[]
const reviewOptions=[{option_id:'fixture-buy-carry',action:'buy',expected_placement:3.1,standard_error:.2},{option_id:'fixture-hold-gold',action:'hold',expected_placement:4.2,standard_error:.3},{option_id:'fixture-buy-tank',action:'buy',expected_placement:3.5,standard_error:.25}]
const reviewMoment={moment_id:'fixture-moment',engine_decision_id:'fixture-engine',moment_path:['moments',0],round_id:'3-2',category:'shop',cost:-1.1,close_call:false,reason:'synthetic_already_scored_choice',shown:{status:'unavailable'},engine_choice:reviewOptions[0],player_choice:reviewOptions[1],unavailable:{follow:'display_attribution_unavailable'},keyframe:{media_name:'media/'+('a'.repeat(32))+'.webp',reason:null,logged_reason:'synthetic_choice_change',timestamp:'2026-10-13T12:00:00Z',log_seq:7}}
let keyframeBytes:Promise<Uint8Array>|null=null
// Synthetic typed review sections in the shapes of tft_review.sections.surface_sections.
const lineHeader=(id:string,levels:Record<string,number>,rolls:Record<string,number>,expected:number,gold:number[])=>({line_id:id,schedule:{id,levels,rolls,stabilize:false,floor_options:[],family_id:null},expected_placement:expected,standard_error:.2,death_probability:.15,hit_probability:.7,confidence:.5,death_placement_cost:.3,
 projections:gold.map((value,index)=>({round_id:`3-${index+3}`,gold:value,level:6+(index>1?1:0),hp:60-index*6,hit_probability:.7,expected_placement:expected,planned_gold:value}))})
const reviewSurface={surface:{
 lines:[{log_seq:7,round_id:'3-2',observed:{gold:35,level:5,hp:60},pin:{id:'roll:now@30',levels:{'3-2':5},rolls:{'3-2':30},stabilize:false,floor_options:[],family_id:'roll:now'},unavailable:{},recommended:lineHeader('guide:A',{'3-3':6,'4-1':7},{'4-1':20},3.1,[42,48,30]),actual:lineHeader('fitted-hold',{'4-2':7},{},4.2,[50,58,62]),evidence_path:['lines',0]}],
 plan_timeline:[{log_seq:4,round_id:'2-5',status:'open',target:'A',backup:null,candidates:['A','B','C'],called_status:'display_attribution_unavailable',observed_lock:null,pivot_from:null,pivot_to:null,pivot_round:null,rejected_target:null,player_label:'A',divergence_round:null,planning_round:'2-5',target_similarity:.5,evidence_path:['plan_timeline',0]},
  {log_seq:9,round_id:'4-1',status:'committed',target:'B',backup:'A',candidates:['B','A'],called_status:'display_attribution_unavailable',observed_lock:'B',pivot_from:'A',pivot_to:'B',pivot_round:'4-1',rejected_target:'A',player_label:'B',divergence_round:'3-5',planning_round:'4-1',target_similarity:.8,evidence_path:['plan_timeline',1]}],
 fights:[{round_id:'3-2',opponent_id:'p4',start_log_seq:21,start_at:'2026-10-14T18:01:02+00:00',result:'loss',actual_hp_loss:9,win_probability:.42,predicted_hp_loss:7.5,confidence:.6,opponent_warning:null,winner_unit_count:5,winner_unit_count_source:'observed',unavailable:{},evidence_path:['fights',0]},
  {round_id:'3-3',opponent_id:'p6',start_log_seq:30,start_at:'2026-10-14T18:03:10+00:00',result:'win',actual_hp_loss:null,win_probability:null,predicted_hp_loss:null,confidence:null,opponent_warning:null,winner_unit_count:null,winner_unit_count_source:null,unavailable:{forecast:'historical_data_or_prefight_context_unavailable'},evidence_path:['fights',1]}],
 timeline:[{moment_id:'fixture-moment',engine_decision_id:'econ:3-2',log_seq:12,round_id:'3-2',category:'econ',cost:-0.42,paired_uncertainty:.11,close_call:false,differed:true,shown:{status:'unavailable',reason:'display_attribution_unavailable'},reason:'line_projection',unavailable:{},evidence_path:['moments',0]}],
 positioning:[{log_seq:18,engine_decision_id:'positioning:3-2',cost:null,reason:'template_layout',action:'Move to target layout',confidence:.5,layout:[{unit_index:0,unit_id:'TFT18_Shen',cell:3},{unit_index:1,unit_id:'TFT18_Jinx',cell:24}],unavailable:{display:'display_attribution_unavailable'},evidence_path:['positioning',0]}],
}}
async function reviewValue(message:Omit<RequestReview,'v'|'type'|'request_id'>):Promise<Record<string,JsonValue>>{
 if(message.operation==='summary')return reviewLocked?{locked:true,game_id:'123',top5:[]}:{locked:false,game_id:'123',report_id:'fixture-report',evidence_id:'fixture-evidence',placement:{value:4,reason:null},follow_rate:{value:null,reason:'display_attribution_unavailable'},category_costs:{shop:{value:-1.1,reason:null,label:'estimated_signed_cost'}},top5:[reviewMoment]}
 if(reviewLocked)throw new Error('Synthetic review remains locked')
 if(message.operation==='media'){
  if(message.name!==reviewMoment.keyframe.media_name)throw new Error('Unknown synthetic logged media')
  keyframeBytes??=fetch(reviewKeyframe).then(response=>response.arrayBuffer()).then(value=>new Uint8Array(value))
  const bytes=await keyframeBytes,chunk=bytes.slice(message.cursor,message.cursor+message.limit),end=message.cursor+chunk.length
  return {name:message.name,offset:message.cursor,total_bytes:bytes.length,next_cursor:end<bytes.length?end:null,content_type:'image/webp',base64:btoa(String.fromCharCode(...chunk))}
 }
 if(message.report_id!=='fixture-report'||message.evidence_id!=='fixture-evidence')throw new Error('Superseded synthetic review')
 if(message.operation==='tag')return {moment_id:message.moment_id,tag:message.tag}
 if(message.operation==='what_if'){
  const option=reviewOptions.find(option=>option.option_id===message.option_id)
  if(message.moment_id!=='fixture-moment'||!option)throw new Error('Unknown synthetic scored option')
  return {...option,evidence_id:'fixture-evidence',path:[...reviewOptionPath,reviewOptions.indexOf(option)],simulation:'already_scored'}
 }
 let value:JsonValue
 const path=message.path
 if(path.join('/')==='moments/0/evidence_path')value=reviewOptionPath.slice(0,-1)
 else if(path.join('/')===reviewOptionPath.join('/'))value=reviewOptions
 else if(path.length===reviewOptionPath.length+1&&path.slice(0,-1).join('/')===reviewOptionPath.join('/'))value=reviewOptions[Number(path.at(-1))]??null
 else if(path.join('/')==='moments/0')value=reviewMoment
 else if(path[0]==='surface')value=path.reduce<unknown>((node,key)=>(node as Record<string|number,unknown>|undefined)?.[key],reviewSurface) as JsonValue??null
 else value={reason:'Synthetic fixture has no accepted chart DTO for this section'}
 const entries=Array.isArray(value)?value.map((item,index)=>[index,item] as const):typeof value==='object'&&value!==null?Object.entries(value):[[null,value] as const]
 const items=entries.slice(message.cursor,message.cursor+message.limit).map(([key,item])=>({path:key===null?path:[...path,key],...(Array.isArray(item)||typeof item==='object'&&item!==null?{reference:true}:{value:item})}))
 const end=message.cursor+items.length
 return {path,kind:Array.isArray(value)?'array':typeof value==='object'?'object':'value',items,total:entries.length,cursor:message.cursor,next_cursor:end<entries.length?end:null,integer_paths:[]}
}
window.coach = {
  liveShown: message => {
    if(state.mode!=='live'||state.live?.revision!==message.revision)return
    shown.push({surface:message.surface,id:message.decision_id,timestamp:message.timestamp})
    reports.textContent=`Shown events: ${shown.length} · voice: ${shown.filter(row=>row.surface==='voice').length}`
  },
  pinLine: message => {
    if(state.mode!=='live'||state.live?.revision!==message.revision)return
    state={...state,live:{...state.live,pin:message.line_id===null?null:{comp_id:message.comp_id!,line_id:message.line_id,seed:message.seed!}}};publish()
  },
  reviewGames:async()=>({v:1,type:'review_games',request_id:'fixture',games:[{game_id:'123',date:'2026-10-13T00:00:00Z',mode:'silent',finished:true,review_locked:reviewLocked,placement:reviewLocked?null:4,patch:'synthetic'}]}),
  requestReview:async message=>({v:1,type:'review_response',request_id:'fixture',game_id:message.game_id,operation:message.operation,value:await reviewValue(message)}),
  evidencePage: async () => {throw new Error('No recorded evidence page in this fixture')},
  openReview: game_id=>{state={...state,reviewRequest:{game_id,serial:(state.reviewRequest?.serial??0)+1}};publish()},
  overlayInteractive: () => {},
  reportShown: (surface, id, timestamp) => {
    shown.push({ surface, id, timestamp })
    reports.textContent = `Shown events: ${shown.length} · voice: ${shown.filter((row) => row.surface === 'voice').length}`
  },
  getState: async () => structuredClone(state),
  onState: (listener) => {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  setMode: (mode) => {
    if (!canSelectMode(state, mode)) return
    state = {
      ...state,
      mode,
      live:mode==='live'?state.live:null,
      baseline: {
        v: 1,
        type: 'baseline_state',
        mode,
        status: 'Capture OK',
        stale: [],
        content: mode === 'baseline' ? content : null,
        voice: null,
      },
    }
    publish()
  },
  selectGuide: (id) => {
    if (state.mode !== 'baseline') return
    const selected = id === 'guide-a' ? guide : id === 'guide-b' ? guideB : null
    if (!selected) return
    state = {
      ...state,
      baseline: {
        ...state.baseline!,
        content: { ...content, selected },
        voice: null,
      },
    }
    publish()
  },
}
function liveState():LiveState {
 const copy=structuredClone(liveRecording) as unknown as LiveState
 const now=Date.now()
 copy.content!.captured_at=new Date(now).toISOString();copy.content!.evaluated_at=new Date(now).toISOString()
 copy.content!.roster_valid_until=new Date(now+2000).toISOString();copy.content!.ownership_valid_until=new Date(now+2000).toISOString()
 copy.content!.advice=copy.content!.advice.map(row=>({...row,valid_until:row.valid_until===null?null:new Date(now+2000).toISOString()}))
 copy.status='Declared synthetic Engine fixture · renderer only'
 return copy
}
const fixture = {
  live(){
    if(liveRefresh)clearInterval(liveRefresh)
    state={...state,core:'running',mode:'live',availableModes:['silent','baseline','live'],gameflow:{clientRunning:true,phase:'InProgress'},baseline:null,live:liveState()}
    liveRefresh=setInterval(()=>{if(state.mode==='live'&&state.core==='running'&&state.live?.content){const fresh=liveState();state={...state,live:{...fresh,pin:state.live.pin,content:{...fresh.content!,phase:state.live.content.phase,roll_tracker:state.live.content.roll_tracker},observed_phase:state.live.observed_phase}};publish()}},250)
    publish()
  },
  freeze(){if(liveRefresh)clearInterval(liveRefresh);liveRefresh=null},
  roll(){
    if(state.live?.content){state={...state,live:{...state.live,observed_phase:'roll_down',content:{...state.live.content,phase:'roll_down',roll_tracker:{available:false,reason:'No confirmed purchase ledger in this recorded renderer fixture'}}}};publish()}
  },
  review(){
    if(liveRefresh)clearInterval(liveRefresh);liveRefresh=null
    state={...state,core:'running',mode:'baseline',gameflow:{clientRunning:true,phase:'EndOfGame'},live:null,baseline:{v:1,type:'baseline_state',mode:'baseline',status:'Synthetic finished game',content:null,stale:[],voice:null}}
    publish()
  },
  unlockReview(){reviewLocked=false;fixture.review()},
  lockReview(){reviewLocked=true;fixture.review()},
  reset() {
    state = {
      ...state,
      mode: 'baseline',
      gameflow: { clientRunning: true, phase: 'Lobby' },
      baseline: {
        v: 1,
        type: 'baseline_state',
        mode: 'baseline',
        status: 'Capture OK',
        stale: [],
        content: { ...content, selected: guide },
        voice: null,
      },
    }
    publish()
  },
  stale() {
    if(state.mode==='live'&&state.live?.content){state={...state,live:{...state.live,invalidated:Object.fromEntries(state.live.content.advice.map(row=>[row.decision_id,'inventory_complete unread or stale']))}};fixture.freeze();publish();return}
    state = {
      ...state,
      baseline: {
        ...state.baseline!,
        stale: [{ field: 'board', age_seconds: 8, reason: 'board unread' }],
        content:
          state.mode === 'baseline'
            ? {
                ...content,
                selected: guide,
                par: {
                  probability: null,
                  paused: 'own board unread',
                  uncertain: false,
                },
              }
            : null,
      },
    }
    publish()
  },
  stage() {
    state = {
      ...state,
      baseline: {
        ...state.baseline!,
        content:
          state.mode === 'baseline'
            ? { ...content, selected: guide, round_id: '4-1' }
            : null,
        voice:
          state.mode === 'baseline'
            ? {
                id: 'fixture:baseline-stage:4',
                text: 'Fixture next-stage plan.',
              }
            : null,
      },
    }
    publish()
  },
  phase(phase: BaselineContent['phase']) {
    state = {
      ...state,
      baseline: {
        ...state.baseline!,
        content:
          state.mode === 'baseline'
            ? { ...content, selected: guide, phase }
            : null,
      },
    }
    publish()
  },
  restart() {
    state = { ...state, core: 'restarting', baseline: null }
    publish()
  },
  reconnect() {
    state = {
      ...state,
      core: 'running',
      baseline: {
        v: 1,
        type: 'baseline_state',
        mode: state.mode ?? 'silent',
        status: 'Capture OK',
        stale: [],
        content:
          state.mode === 'baseline' ? { ...content, selected: guide } : null,
        voice: null,
      },
    }
    publish()
  },
  unavailable() {
    if(state.mode==='live'&&state.live){fixture.freeze();state={...state,live:{...state.live,content:null,status:'Pinned data unavailable'}};publish();return}
    state = {
      ...state,
      baseline: {
        v: 1,
        type: 'baseline_state',
        mode: state.mode ?? 'silent',
        status: 'Fresh source rejected; validated patch data unavailable',
        stale: [],
        content: null,
        voice: null,
      },
    }
    publish()
  },
}
Object.assign(window, { rendererFixture: fixture })
const controls = document.createElement('div')
controls.style.cssText =
  'display:flex;flex-wrap:wrap;gap:8px;padding:8px;background:#382c14;position:relative;z-index:1000;'
for (const [label, action] of [
  ['Live planning',fixture.live],
  ['Freeze Live capture',fixture.freeze],
  ['Live roll-down',fixture.roll],
  ['Locked review',fixture.lockReview],
  ['Unlocked review fixture',fixture.unlockReview],
  ['Baseline lobby', fixture.reset],
  ['Unread board', fixture.stale],
  ['Disconnect', fixture.restart],
  ['Reconnect', fixture.reconnect],
  ['Data unavailable', fixture.unavailable],
  ['Stage start', fixture.stage],
] as const) {
  const button = document.createElement('button')
  button.textContent = label
  button.addEventListener('click', action)
  controls.append(button)
}
reports.textContent = 'Shown events: 0 · voice: 0'
controls.append(reports)
document.querySelector('#root')!.before(controls)
if(new URLSearchParams(location.search).get('mode')==='live')fixture.live()
void import('../../src/renderer/src/main')
