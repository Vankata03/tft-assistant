import {useReviewNoticeShown} from './noticeShown'
import type {ShellState} from '../../../shared/state'

export function ReviewReadyNotice({state,overlay=false}:{state:ShellState;overlay?:boolean}):React.JSX.Element|null{
 const ready=state.reviewReady
 const inGame=['InProgress','Reconnect','PreEndOfGame'].includes(state.gameflow?.phase??'')
 const anchor=overlay&&state.overlayGeometry?.bounds?state.overlayGeometry.anchors.find(row=>row.kind==='review'):null
 const enabled=state.core==='running'&&!!ready&&['baseline','live'].includes(ready.mode)&&!inGame&&(!overlay||!!anchor)
 const {element,shownAt}=useReviewNoticeShown(ready,enabled,overlay?'overlay':'status')
 if(!enabled||!ready)return null
 const at=shownAt??ready.displayed_at
 const latency=at?(Date.parse(at)-Date.parse(ready.ended_at))/1000:null
 return <div ref={element} className={overlay?'overlay-tag review-ready-toast':'status-banner review-ready-notice'} style={anchor?{left:`${anchor.x*100}%`,top:`${anchor.y*100}%`,width:`${anchor.width*100}%`}:undefined}
  onMouseEnter={()=>{if(overlay)window.coach?.overlayInteractive(true)}} onMouseLeave={()=>{if(overlay)window.coach?.overlayInteractive(false)}}>
  <button onClick={()=>window.coach?.openReview(ready.game_id)}>Review ready · game {ready.game_id}</button>
  {latency!==null&&latency>30?<span> · late ({latency.toFixed(1)} s after logged game end)</span>:null}
 </div>
}
