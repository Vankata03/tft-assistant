import {useEffect,useState} from 'react'
import type {JsonValue,RequestReview,ReviewGames} from '../../../shared/messages'
import type {ShellState} from '../../../shared/state'
import './review.css'
import {RecordedChoice,ReviewMoment} from './ReviewMoment'

type Document=Record<string,unknown>
const documentValue=(value:unknown):Document=>typeof value==='object'&&value!==null&&!Array.isArray(value)?value as Document:{}
const metric=(value:unknown):string=>{const row=documentValue(value);return typeof row.value==='number'?row.value.toFixed(2):`Unavailable · ${String(row.reason??'not recorded')}`}
const humanReason=(value:unknown):string=>String(value??'not recorded').replaceAll('_',' ')
export interface ReviewSummaryProps {summary:Document;onMoment(id:string,path:readonly(string|number)[]|null):void;onTag(id:string,tag:'agree'|'disagree'|'unsure'):void}
export function ReviewSummaryView({summary,onMoment,onTag}:ReviewSummaryProps):React.JSX.Element{
 if(summary.locked)return <section className="panel" role="status"><h2>Review locked</h2><p>This Silent game's review unlocks when the Live-mode run starts.</p></section>
 const top5=Array.isArray(summary.top5)?summary.top5.map(documentValue):[]
 return <section className="review-summary panel"><h2>Game {String(summary.game_id)} review</h2>
  <div className="review-metrics"><p>Placement <strong>{metric(summary.placement)}</strong></p><p>Follow rate <strong>{metric(summary.follow_rate)}</strong></p></div>
  <h3>Estimated signed cost by category</h3><p className="subtle">Engine placement minus player placement. Negative values indicate worse player outcomes; estimates remain distinct from observed results.</p>
  <div className="review-costs">{Object.entries(documentValue(summary.category_costs)).map(([category,value])=><p key={category}>{category}: <strong>{metric(value)}</strong></p>)}</div>
  <h3>Top 5 moments</h3>{top5.length?top5.map(moment=><article className="review-moment" key={String(moment.moment_id)}>
   <strong>{String(moment.round_id)} · {String(moment.category)}</strong><p>Estimated signed cost {typeof moment.cost==='number'?moment.cost.toFixed(2):'unavailable'}{moment.close_call?' · close call':''}</p>
   <p>{String(moment.reason??'Reason unavailable').replaceAll('_',' ')} · shown: {String(documentValue(moment.shown).status??'unavailable')}</p>
   <div className="review-choice-pair"><RecordedChoice label="Engine choice" value={moment.engine_choice} unavailable={documentValue(moment.unavailable).engine_choice}/><RecordedChoice label="Player choice" value={moment.player_choice} unavailable={documentValue(moment.unavailable).player_choice}/></div>
   <p className="subtle">Keyframe: {typeof documentValue(moment.keyframe).media_name==='string'?'Logged capture available':humanReason(documentValue(moment.keyframe).reason)}</p>
   <button onClick={()=>onMoment(String(moment.moment_id),Array.isArray(moment.moment_path)?moment.moment_path as (string|number)[]:null)}>Expand scored moment</button>
   <span className="review-tags">{(['agree','disagree','unsure'] as const).map(tag=><button key={tag} onClick={()=>onTag(String(moment.moment_id),tag)}>{tag}</button>)}</span>
  </article>):<p>No qualified harmful or differing moments are available.</p>}
 </section>
}

export function ReviewPanel({state,onOpenChange}:{state:ShellState;onOpenChange?:(open:boolean)=>void}):React.JSX.Element|null{
 const [open,setOpen]=useState(false),[games,setGames]=useState<ReviewGames['games']>([]),[game,setGame]=useState<string|null>(null),[summary,setSummary]=useState<Document|null>(null),[error,setError]=useState<string|null>(null)
 const [path,setPath]=useState<readonly(string|number)[]|null>(null),[cursor,setCursor]=useState(0),[page,setPage]=useState<Document|null>(null),[notice,setNotice]=useState<string|null>(null),[selectedMoment,setSelectedMoment]=useState<Document|null>(null)
 const suppressed=state.core!=='running'||(state.mode==='silent'&&['InProgress','Reconnect','PreEndOfGame'].includes(state.gameflow?.phase??''))
 useEffect(()=>{if(state.reviewRequest&&!suppressed){setGame(state.reviewRequest.game_id);setOpen(true)}},[state.reviewRequest?.serial,suppressed])
 useEffect(()=>{onOpenChange?.(open&&!suppressed)},[open,suppressed,onOpenChange])
 const request=(operation:RequestReview['operation'],arguments_:Partial<Omit<RequestReview,'v'|'type'|'request_id'>>={})=>{
  if(!game)return Promise.reject(new Error('Select a logged game'))
  return window.coach.requestReview({game_id:game,operation,report_id:typeof summary?.report_id==='string'?summary.report_id:null,evidence_id:typeof summary?.evidence_id==='string'?summary.evidence_id:null,path:[],cursor:0,limit:32,moment_id:null,option_id:null,tag:null,name:null,...arguments_})
 }
 useEffect(()=>{if(suppressed){setOpen(false);setSummary(null);setPage(null);setPath(null);setSelectedMoment(null)}},[suppressed])
 useEffect(()=>{
  if(!open||suppressed)return
  let active=true
  setError(null)
  void window.coach.reviewGames().then(response=>{if(active)setGames(response.games)}).catch((e:unknown)=>{if(active)setError(String(e))})
  return()=>{active=false}
 },[open,suppressed])
 useEffect(()=>{
  if(!open||suppressed||!game)return
  let active=true;setSummary(null);setPath(null);setPage(null);setSelectedMoment(null);setError(null)
  void window.coach.requestReview({game_id:game,operation:'summary',report_id:null,evidence_id:null,path:[],cursor:0,limit:32,moment_id:null,option_id:null,tag:null,name:null}).then(response=>{if(active)setSummary(response.value)}).catch((e:unknown)=>{if(active)setError(String(e))})
  return()=>{active=false}
 },[game,open,suppressed])
 useEffect(()=>{
  if(!path||!summary||suppressed)return
  let active=true;setPage(null);setError(null)
  void request('page',{path:[...path],cursor}).then(response=>{if(active)setPage(response.value)}).catch((e:unknown)=>{if(active)setError(String(e))})
  return()=>{active=false}
 },[path,cursor,summary?.report_id,suppressed])
 if(suppressed)return null
 const browse=(next:readonly(string|number)[])=>{setPath(next);setCursor(0)}
 return <section className="review-shell">
  <button onClick={()=>setOpen(!open)} aria-expanded={open}>{open?'Close review':'Post-game review'}</button>
  {open?<div className="review-grid"><aside className="panel"><h2>Logged games</h2>{games.map(row=><button className="review-game" disabled={!row.finished} key={String(row.game_id)} onClick={()=>setGame(String(row.game_id))}>{String(row.game_id)} · {String(row.mode)} · {row.review_locked?'locked':row.placement===null?'placement unavailable':`placement ${String(row.placement)}`}</button>)}</aside><div>
   {error?<p role="alert" className="status-banner">{error}</p>:null}{notice?<p role="status">{notice}</p>:null}
   {summary?<ReviewSummaryView summary={summary} onMoment={(id)=>{setPath(null);setSelectedMoment((Array.isArray(summary.top5)?summary.top5.map(documentValue):[]).find(moment=>moment.moment_id===id)??null)}} onTag={(moment_id,tag)=>{void request('tag',{moment_id,tag}).then(()=>setNotice(`Saved ${tag}`)).catch((e:unknown)=>setError(String(e)))}}/>:game?<p role="status">Loading protected review…</p>:<p>Select a finished logged game.</p>}
   {summary&&!summary.locked?<>{selectedMoment?<ReviewMoment key={`${summary.report_id}:${String(selectedMoment.moment_id)}`} moment={selectedMoment} request={async(operation,args)=>(await request(operation,args)).value} onDebug={browse}/>:null}<nav className="review-sections">{[['Game plan','plan_timeline'],['Lines · actual / recommended / pinned','lines'],['Fights · forecast / result','fights'],['Full round timeline','timeline'],['Positioning','positioning'],['Debug','debug']] .map(([label,key])=><button key={key} onClick={()=>browse([key!])}>{label}</button>)}</nav>
    {path?<section className="panel review-evidence"><h3>{path.join(' / ')}</h3>{path.length?<button onClick={()=>browse(path.slice(0,-1))}>Parent evidence</button>:null}
     {!page?<p>Loading bounded evidence…</p>:<>{Array.isArray(page.items)?page.items.map((raw,index)=>{const row=documentValue(raw),location=Array.isArray(row.path)?row.path as (string|number)[]:[];return <article key={`${cursor}:${index}`}><strong>{String(location.at(-1)??index)}</strong>{row.reference?<button onClick={()=>browse(location)}>Open recorded evidence</button>:<pre>{typeof row.value==='string'?row.value:JSON.stringify(row.value,null,2)}</pre>}</article>}):null}
      <div className="page-controls"><button disabled={cursor===0} onClick={()=>setCursor(Math.max(0,cursor-32))}>Previous</button><button disabled={typeof page.next_cursor!=='number'} onClick={()=>setCursor(Number(page.next_cursor))}>Next</button></div></>}
    </section>:null}
   </>:null}
  </div></div>:null}
 </section>
}
