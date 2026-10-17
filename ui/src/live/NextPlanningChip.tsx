import {useLivePreviewShown} from './previewShown'
import type {LiveState,LiveSurfaceAnchor} from '../shared/messages'

/** Combat's one chip: the next scheduled point of this round's qualified plan, never projected state. */
export function NextPlanningChip({view,anchor}:{view:LiveState;anchor:LiveSurfaceAnchor|undefined}):React.JSX.Element|null{
 const preview=view.content?.next_planning??null
 const paused=!preview?.available?preview?.reason??'next planning call unavailable':view.next_planning_invalidated??null
 const ref=useLivePreviewShown<HTMLDivElement>(view,Boolean(anchor&&preview?.available&&!paused))
 if(!anchor)return null
 const steps=preview&&!paused?[preview.level===null?null:`level ${preview.level}`,preview.gold_floor===null?null:`roll to ${preview.gold_floor} gold`].filter(Boolean).join(', '):''
 return <div ref={ref} className={`overlay-tag next-planning ${paused?'paused':''}`} style={{left:`${anchor.x*100}%`,top:`${anchor.y*100}%`,width:`${anchor.width*100}%`}}>
  <span>{paused?`paused · ${paused}`:`Next planning · ${preview!.line_id} · ${steps} at ${preview!.round_id}`}</span>
  {preview?.available&&!paused?<span className="overlay-tooltip">planned in {preview.planning_round}{preview.pinned?' · pinned Line':''} · scheduled point only</span>:null}
 </div>
}
