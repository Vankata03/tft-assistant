import {useState} from 'react'
import type {LiveAdviceDisplay,LiveState,LiveSurfaceAnchor,LiveLineDisplay} from '../shared/messages'
import type {ShellState} from '../shared/state'
import {useLiveShown} from './shown'
import {NextPlanningChip} from './NextPlanningChip'

function advicePaused(row:LiveAdviceDisplay,view:LiveState,now:number):boolean{
 return Boolean(row.payload.paused)||Boolean(view.invalidated?.[row.decision_id])||(row.valid_until!==null&&(!Number.isFinite(Date.parse(row.valid_until))||Date.parse(row.valid_until)<now))
}
type Tag={row:LiveAdviceDisplay;anchor:LiveSurfaceAnchor;text:string;line?:boolean}
function AdviceTag({tag,view,now,onPin}:{tag:Tag;view:LiveState;now:number;onPin:(line:LiveLineDisplay|null)=>void}):React.JSX.Element{
 const [open,setOpen]=useState(false)
 const {row,anchor}=tag
 const paused=advicePaused(row,view,now)
 const uncertain=row.confidence<(view.content?.confidence_medium_min??1)
 const ref=useLiveShown<HTMLDivElement>(view,row,'overlay',!paused)
 return <div ref={ref} className={`overlay-tag ${paused||uncertain?'paused':''} ${row.payload.pin_alternative?'pin-warning':''}`} style={{left:`${anchor.x*100}%`,top:`${anchor.y*100}%`,width:`${anchor.width*100}%`}}>
  {tag.line?<div className="line-widget" onMouseEnter={()=>window.coach?.overlayInteractive(true)} onMouseLeave={()=>window.coach?.overlayInteractive(false)}>
   <button disabled={paused} onClick={()=>setOpen(!open)} aria-expanded={open}>{paused?'paused · Line evidence':tag.text}{uncertain?' ?':''}</button>
   {open?<div className="overlay-lines">{view.content?.lines.map(line=><button key={line.line_id} disabled={paused} onClick={()=>onPin(view.pin?.line_id===line.line_id?null:line)}>{line.line_id} · {line.expected_placement.toFixed(2)} {view.pin?.line_id===line.line_id?'unpin':'pin'}</button>)}<button onClick={()=>{setOpen(false);window.coach?.overlayInteractive(false)}}>Close Lines</button></div>:null}
  </div>:<span>{paused?`paused · ${String(view.invalidated?.[row.decision_id]??row.payload.reason??'required evidence expired')}`:tag.text}{uncertain?' ?':''}</span>}
  <span className="overlay-tooltip">{row.reason.replaceAll('_',' ')}{row.payload.pin_alternative?` · ${String(row.payload.pin_alternative)} improves by ${String(row.payload.pin_gap)}`:''}</span>
 </div>
}
export function LiveOverlay({state,onPin,now}:{state:ShellState;onPin:(line:LiveLineDisplay|null)=>void;now:number}):React.JSX.Element|null{
 const view=state.core==='running'&&state.mode==='live'&&state.live?.mode==='live'?state.live:null
 const projection=state.overlayGeometry
 if(!view?.content||!projection?.bounds||!projection.anchors.length)return null
 const content=view.content,phase=view.observed_phase??content.phase,names=content.entity_names
 const ownershipFresh=view.ownership_qualified!==false&&content.ownership_valid_until!==null&&Date.parse(content.ownership_valid_until)>=now
 const trackerFresh=ownershipFresh&&content.advice.some(row=>row.domain==='econ'&&!advicePaused(row,view,now))
 const tags:Tag[]=[]
 const anchor=(kind:string,index:number)=>projection.anchors.find(row=>row.kind===kind&&row.index===index)
 for(const row of content.advice){
  const invalid=view.invalidated?.[row.decision_id]
  if(invalid&&!invalid.includes('unread')&&!invalid.includes('stale'))continue
  if(['planning','roll_down'].includes(phase)){
   if(row.domain==='shop'&&Array.isArray(row.payload.buys))for(const buy of row.payload.buys as {slot:number;unit_id:string}[]){const at=anchor('shop',buy.slot);if(at)tags.push({row,anchor:at,text:`Buy ${names[buy.unit_id]??buy.unit_id}`})}
   if(row.domain==='wisp'&&row.payload.operation==='buy'){const at=anchor('wisp',Number(row.payload.slot))??anchor('shop',Number(row.payload.slot));if(at)tags.push({row,anchor:at,text:'Buy Wisp'})}
   if(row.domain==='econ'){const at=anchor('line',0)??anchor('level',0);if(at)tags.push({row,anchor:at,text:`${String(row.payload.line_id??row.action)} · ${row.numbers.expected_placement??'unavailable'}${row.payload.pin_alternative?` · ${String(row.payload.pin_alternative)} better by ${typeof row.payload.pin_gap==='number'?row.payload.pin_gap.toFixed(2):'unavailable'}`:''}`,line:true});if(row.action==='Level now'){const xp=anchor('xp',0);if(xp)tags.push({row,anchor:xp,text:'Level now'})}}
  }else if(phase==='augment'&&row.domain==='augment'){
   if(row.payload.operation==='reroll'&&Array.isArray(row.payload.slots))for(const slot of row.payload.slots){const at=anchor('augment',Number(slot));if(at)tags.push({row,anchor:at,text:'Reroll'})}
   else for(const option of row.options){if(typeof option.payload.slot!=='number')continue;const at=anchor('augment',option.payload.slot);if(at)tags.push({row,anchor:at,text:`${option.option_id===row.option_id?'Take · ':''}${typeof option.payload.placement_gain==='number'?`${option.payload.placement_gain.toFixed(2)} placement gain`:option.expected_placement===null?'placement unavailable':`expected ${option.expected_placement.toFixed(2)}`}`})}
  }else if(phase==='carousel'&&row.domain==='carousel'&&Array.isArray(row.payload.ranking)){
   for(const [rank,id] of row.payload.ranking.slice(0,2).entries()){const option=row.options.find(option=>option.option_id===id);const at=option?anchor('carousel',Number(option.payload.slot)):null;if(at)tags.push({row,anchor:at,text:String(rank+1)})}
  }
 }
 const target=content.advice.find(row=>row.domain==='positioning'&&row.payload.operation==='layout'&&!view.invalidated?.[row.decision_id])
 const layout=target?.payload.layout as {cell:number;unit_id:string}[]|undefined
 const arrows=target?.payload.arrows as {from:number;to:number}[]|undefined
 return <div className="baseline-overlay live-overlay" aria-label="Live overlay">
  {tags.map((tag,index)=><AdviceTag key={`${tag.row.decision_id}:${tag.anchor.kind}:${tag.anchor.index}:${index}`} tag={tag} view={view} now={now} onPin={onPin}/>)}
  {['planning','roll_down'].includes(phase)?content.opponents.filter(row=>view.roster_qualified!==false&&content.roster_valid_until!==null&&Date.parse(content.roster_valid_until)>=now&&row.scout_due&&Number.isInteger(row.player_row_index)).map(row=>{const at=anchor('player',Number(row.player_row_index));return at?<div key={String(row.opponent_id)} className="overlay-tag scout-eye" style={{left:`${at.x*100}%`,top:`${at.y*100}%`}}>◉ {row.age_rounds===null?'never':`${row.age_rounds}r`}<span className="overlay-tooltip">Scout {String(row.name)} · trait-only sighting</span></div>:null}):null}
  {phase==='planning'&&target&&layout?layout.map((row,index)=>{const at=anchor('hex',row.cell);return at?<AdviceTag key={`hex:${index}`} tag={{row:target,anchor:at,text:names[row.unit_id]??row.unit_id}} view={view} now={now} onPin={onPin}/>:null}):null}
  {phase==='planning'&&target&&!advicePaused(target,view,now)&&arrows?<svg className="layout-arrows" viewBox="0 0 100 100" preserveAspectRatio="none"><defs><marker id="arrowhead" markerWidth="4" markerHeight="4" refX="3" refY="2" orient="auto"><path d="M0,0 L4,2 L0,4" fill="currentColor"/></marker></defs>{arrows.map((row,index)=>{const from=anchor('hex',row.from),to=anchor('hex',row.to);return from&&to?<line key={index} x1={(from.x+from.width/2)*100} y1={(from.y+from.height/2)*100} x2={(to.x+to.width/2)*100} y2={(to.y+to.height/2)*100} markerEnd="url(#arrowhead)"/>:null})}</svg>:null}
  {phase==='combat'?<NextPlanningChip view={view} anchor={anchor('line',0)??anchor('level',0)}/>:null}
  {phase==='roll_down'&&trackerFresh&&content.roll_tracker?.available?<div className="roll-tracker">Floor {String(content.roll_tracker.gold_floor)} · {String(content.roll_tracker.rolls_left)} rolls left · {(content.roll_tracker.units as {unit_id:string;copies:number;goal:number;in_shop:boolean;hit_probability:number}[]).map(row=><span key={row.unit_id}>{names[row.unit_id]??row.unit_id} {row.copies}/{row.goal} · {Math.round(row.hit_probability*100)}%{row.in_shop?' · in shop':''}</span>)}</div>:null}
 </div>
}
