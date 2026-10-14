import {useEffect,useState} from 'react'
import type {LiveAdviceDisplay,LiveLineDisplay,LiveState} from '../shared/messages'
import type {SessionMode} from '../shared/protocol'
import {describeCore,type ShellState} from '../shared/state'
import {useLiveShown} from './shown'
import {SessionModeSelector} from '../renderer/src/ModeSelector'
import {describeSchedule} from '../renderer/src/lineSchedule'

export interface LiveCockpitProps {
 state:ShellState
 onMode(mode:SessionMode):void
 onPin(line:LiveLineDisplay|null):void
 onDetail(path:readonly(string|number)[]):void
 now?:number
}

function AdviceCard({row,now,onDetail,invalidated,view}:{row:LiveAdviceDisplay;view:LiveState;now:number;invalidated?:string;onDetail(path:readonly(string|number)[]):void}):React.JSX.Element{
 const [expanded,setExpanded]=useState(false)
 const expired=row.valid_until!==null&&Date.parse(row.valid_until)<now
 const paused=Boolean(row.payload.paused)||expired||Boolean(invalidated)
 const low=view.content?.confidence_medium_min===null||row.confidence<(view.content?.confidence_medium_min??1)
 const visible=useLiveShown(view,row,'cockpit',!paused)
 return <article ref={visible} className={`live-advice ${paused?'paused':''} ${low?'confidence-low':''}`} data-decision={row.decision_id}>
  <div className="live-advice-heading"><span className="domain-label">{row.domain}</span><strong>{paused?`Paused · ${invalidated??(expired?'required evidence expired':String(row.payload.reason??'unread field'))}`:row.action}</strong></div>
  {low?<p className="subtle">Low confidence · ?</p>:null}
  <p className="subtle">{row.reason.replaceAll('_',' ')}</p>
  {Array.isArray(row.payload.missing)?<p className="subtle">Unread: {row.payload.missing.join(', ')}</p>:null}
  <div className="live-numbers">{Object.entries(row.numbers).map(([key,value])=><span key={key}>{key.replaceAll('_',' ')}: {typeof value==='number'?value.toFixed(2):value}</span>)}</div>
  {row.options.length?<button onClick={()=>setExpanded(!expanded)} aria-expanded={expanded}>Compare {row.options.length} scored options</button>:null}
  {expanded?<ol className="live-options">{row.options.map(option=><li key={option.option_id}><strong>{option.action} · {String(option.payload.id??option.payload.augment_id??option.payload.item_id??option.payload.unit_id??option.option_id)}</strong> · {option.expected_placement===null?'placement unavailable':`expected ${option.expected_placement.toFixed(2)}`}{option.standard_error===null?'':` ± ${option.standard_error.toFixed(2)}`}{option.payload.levels||option.payload.rolls?<span className="subtle"> · {option.payload.levels?`levels ${JSON.stringify(option.payload.levels)}`:''}{option.payload.rolls?` rolls ${JSON.stringify(option.payload.rolls)}`:''}</span>:null}<button onClick={()=>onDetail(option.evidence_path)}>Evidence</button></li>)}</ol>:null}
 </article>
}

export function LiveCockpit({state,onMode,onPin,onDetail,now:clockOverride}:LiveCockpitProps):React.JSX.Element{
 const [clock,setClock]=useState(Date.now)
 useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),100);return()=>clearInterval(timer)},[])
 const now=clockOverride??clock
 const view=state.core==='running'&&state.mode==='live'&&state.live?.mode==='live'?state.live:null
 const content=view?.content
 const names=content?.entity_names??{}
 const econ=content?.advice.find(row=>row.domain==='econ')
 const pinsAllowed=Boolean(econ&&!econ.payload.paused&&!view?.invalidated?.[econ.decision_id]&&(econ.valid_until===null||Date.parse(econ.valid_until)>=now)&&['planning','roll_down'].includes(view?.observed_phase??content?.phase??'unknown'))
 const rosterFresh=view?.roster_qualified!==false&&Boolean(content?.roster_valid_until&&Date.parse(content.roster_valid_until)>=now)
 const ownershipFresh=view?.ownership_qualified!==false&&Boolean(content?.ownership_valid_until&&Date.parse(content.ownership_valid_until)>=now)
 const layout=content?.advice.find(row=>row.domain==='positioning'&&Array.isArray(row.payload.layout))?.payload.layout as {unit_id:string;cell:number}[]|undefined
 return <main className="cockpit live-cockpit">
  <header className="app-header"><h1>TFT Assistant</h1><SessionModeSelector state={state} onChange={onMode}/><span className="connection">{describeCore(state.core)}</span>{content?<span className="patch">{content.round_id} · {content.phase}</span>:null}</header>
  {state.error?<p role="alert" className="status-banner">{state.error}</p>:null}
  {state.baseline?.mode==='live'&&state.baseline.stale.length?<div className="status-banner paused" role="status">{state.baseline.stale.map(row=><span key={row.field}>Paused · {row.reason}{row.age_seconds===null?'':` · ${Math.round(row.age_seconds)}s`}</span>)}</div>:null}
  {state.baseline?.status&&state.baseline.status!=='Capture OK'?<p className="status-banner">{state.baseline.status}</p>:null}
  {content?.warnings.length?<p className="status-banner">{content.warnings.join(' · ')}</p>:null}
  {state.surfaceGeometry?.geometry?.window_mode==='exclusive_fullscreen'?<p className="status-banner">Exclusive fullscreen · overlay off; use windowed or borderless.</p>:null}
  {!content?<p className="status-banner">{state.mode==='silent'?'Silent game · logging':state.core!=='running'?'Coach restarting':view?.status??'Live content unavailable'}</p>:<>
   <div className="live-cockpit-grid">
    <section className="panel live-current"><h2>Current advice</h2>{content.advice.map((row,index)=><AdviceCard key={`${row.decision_id}:${row.option_id}:${index}`} row={row} view={view} now={now} invalidated={view.invalidated?.[row.decision_id]} onDetail={onDetail}/>)}</section>
    <div className="live-plan-column">
     <section className="panel"><h2>Game plan</h2><p className="live-plan-name">{String(content.plan.target??'Open plan')}</p><p className="subtle">{String(content.plan.status??'Unavailable')} · backup {String(content.plan.backup??'unavailable')}</p><p className="subtle">{Array.isArray(content.plan.candidates)&&content.plan.candidates.length?`Candidates ${content.plan.candidates.map(String).join(', ')}`:'No candidate comps'}</p>{content.plan.pivot_to?<p>Pivot {String(content.plan.pivot_from??'unread')} → {String(content.plan.pivot_to)} at {String(content.plan.pivot_round??'unread')}</p>:null}<p className="subtle">Complete own ownership is required for authoritative projections.</p></section>
     <section className="panel"><h2>Line projection</h2>{content.projection.length?<div className="table-scroll"><table><thead><tr><th>Round</th><th>Level</th><th>Gold</th><th>Hit</th><th>HP</th><th>Placement</th></tr></thead><tbody>{content.projection.map(row=><tr key={row.round_id}><td>{row.round_id}</td><td>{row.level.toFixed(1)}</td><td>{row.gold.toFixed(0)}</td><td>{Math.round(row.hit_probability*100)}%</td><td>{row.hp.toFixed(0)}</td><td>{row.expected_placement.toFixed(2)}</td></tr>)}</tbody></table></div>:<p className="subtle">No current qualified Line projection.</p>}
      <div className="line-candidates">{content.lines.map(line=><div className={`line-candidate ${view.pin?.line_id===line.line_id?'pinned':''}`} key={`${line.comp_id}:${line.line_id}`}><span>{line.line_id}<small className="subtle"> · {describeSchedule(line.schedule)} · hit {Math.round(line.hit_probability*100)}% · death {Math.round(line.death_probability*100)}%</small></span><strong>{line.expected_placement.toFixed(2)}</strong><button disabled={!pinsAllowed} onClick={()=>onPin(view.pin?.line_id===line.line_id?null:line)}>{view.pin?.line_id===line.line_id?'Unpin':'Pin Line'}</button><button onClick={()=>onDetail(line.evidence_path)}>Projection</button></div>)}</div>
     </section>
     <section className="panel"><h2>Target layout</h2><div className="live-target-layout" aria-label="Target board hexes">{Array.from({length:28},(_,cell)=><div className="hex-cell" key={cell}>{layout?.filter(row=>row.cell===cell).map((row,index)=><strong key={index}>{names[row.unit_id]??row.unit_id}</strong>)??cell+1}</div>)}</div><p className="subtle">Move arrows require a positively known current hex; tracked units need only their target hex.</p></section>
    </div>
    <aside className="live-opponent-column"><section className="panel"><h2>Opponents</h2>{content.opponents.length?<div className="opponent-table">{content.opponents.map(row=><article key={String(row.opponent_id)} className={`opponent-row freshness-${row.age_rounds===null?'never':Number(row.age_rounds)<=1?'fresh':Number(row.age_rounds)<=3?'aging':'old'}`}>
 <strong>{String(row.name)}</strong><span>Win {row.win_probability===null||!ownershipFresh?'unavailable':`${Math.round(Number(row.win_probability)*100)}%`}</span><span>{row.age_rounds===null?'Never scouted':`${row.age_rounds} rounds old`}</span>
 <p>Next {row.next_probability===null||!rosterFresh?'unavailable':`${Math.round(Number(row.next_probability)*100)}%`}{row.scout_due&&rosterFresh?' · scout due':''}</p>
 <p className="subtle">Traits {row.traits===null?'unread':Object.entries(row.traits as Record<string,number>).map(([id,count])=>`${names[id]??id} ${count}`).join(', ')}</p>
 <p className="subtle">Threat tags {Array.isArray(row.threat_tags)&&row.threat_tags.length?row.threat_tags.join(', '):'unavailable'}</p>
 <p className="subtle">Inferred units · certainty {row.inference_certainty===null?'unavailable':`${Math.round(Number(row.inference_certainty)*100)}%`}</p>
 <p>{Object.entries(row.unit_probabilities as Record<string,number>).sort((a,b)=>b[1]-a[1]).map(([id,p])=>`${names[id]??id} ${Math.round(p*100)}%`).join(', ')||'No supported posterior'}</p>
 </article>)}</div>:<p className="subtle">Opponent evidence unavailable.</p>}</section><section className="panel"><h2>Roll-down tracker</h2>{content.roll_tracker?.available?<><p>Floor {String(content.roll_tracker.gold_floor)} gold · {String(content.roll_tracker.rolls_left)} rolls left</p>{(content.roll_tracker.units as {unit_id:string;copies:number;goal:number;in_shop:boolean;hit_probability:number}[]).map(row=><p key={row.unit_id}>{names[row.unit_id]??row.unit_id} · {row.copies}/{row.goal} copies · {Math.round(row.hit_probability*100)}%{row.in_shop?' · in shop':''}</p>)}</>:<p className="subtle">{String(content.roll_tracker?.reason??'Waiting for a confirmed roll-down and complete purchase tracking.')}</p>}</section><section className="panel"><h2>Comp comparison</h2>{content.fits.map(fit=><p className="live-fit" key={fit.comp_id}><span>{fit.comp_id}</span><strong>{fit.score.toFixed(2)}</strong><button onClick={()=>onDetail(fit.evidence_path)}>Evidence</button></p>)}</section></aside>
   </div>
  </>}
 </main>
}
