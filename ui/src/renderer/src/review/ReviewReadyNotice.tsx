import type {ShellState} from '../../../shared/state'

export function ReviewReadyNotice({state,overlay=false}:{state:ShellState;overlay?:boolean}):React.JSX.Element|null{
 const ready=state.reviewReady
 const inGame=['InProgress','Reconnect','PreEndOfGame'].includes(state.gameflow?.phase??'')
 if(state.core!=='running'||!ready||!['baseline','live'].includes(ready.mode)||inGame)return null
 const anchor=overlay&&state.overlayGeometry?.bounds?state.overlayGeometry.anchors.find(row=>row.kind==='review'):null
 if(overlay&&!anchor)return null
 return <div className={overlay?'overlay-tag review-ready-toast':'status-banner review-ready-notice'} style={anchor?{left:`${anchor.x*100}%`,top:`${anchor.y*100}%`,width:`${anchor.width*100}%`}:undefined}
  onMouseEnter={()=>{if(overlay)window.coach?.overlayInteractive(true)}} onMouseLeave={()=>{if(overlay)window.coach?.overlayInteractive(false)}}>
  <button onClick={()=>window.coach?.openReview(ready.game_id)}>Review ready · game {ready.game_id}</button>
  {ready.late?<span> · late ({ready.latency_seconds.toFixed(1)} s after logged game end)</span>:null}
 </div>
}
