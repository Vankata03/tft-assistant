import {useEffect,useRef} from 'react'
import type {LiveAdviceDisplay,LiveState} from '../shared/messages'

/** A mounted row is acknowledged only after visible paint in the actual window. */
export function useLiveShown<T extends HTMLElement=HTMLElement>(view:LiveState|null, row:LiveAdviceDisplay, surface:'cockpit'|'overlay',enabled:boolean){
 const element=useRef<T>(null)
 useEffect(()=>{
  const node=element.current
  if(!node||!enabled||!view?.content||!view.revision||typeof IntersectionObserver==='undefined')return
  let sent=false,frame=0,intersecting=false
  const actuallyVisible=()=>{
   const b=node.getBoundingClientRect()
   const area=b.width*b.height
   const intersection=Math.max(0,Math.min(b.right,innerWidth)-Math.max(b.left,0))*Math.max(0,Math.min(b.bottom,innerHeight)-Math.max(b.top,0))
   return intersecting&&document.visibilityState==='visible'&&node.isConnected&&area>0&&intersection/area>=.5&&(row.valid_until===null||Date.parse(row.valid_until)>=Date.now())
  }
  const visible=()=>{
   if(sent||!actuallyVisible())return
   cancelAnimationFrame(frame)
   frame=requestAnimationFrame(()=>{
    if(sent||!actuallyVisible())return
    sent=true
    window.coach?.liveShown({game_id:view.content!.game_id,revision:view.revision!,decision_id:row.decision_id,option_id:row.option_id,surface,timestamp:new Date().toISOString()})
   })
  }
  const observer=new IntersectionObserver(entries=>{for(const entry of entries){if(entry.target===node)intersecting=entry.isIntersecting&&entry.intersectionRatio>=.5}visible()},{threshold:.5})
  observer.observe(node)
  document.addEventListener('visibilitychange',visible)
  return()=>{observer.disconnect();cancelAnimationFrame(frame);document.removeEventListener('visibilitychange',visible)}
 },[view?.revision,row.decision_id,row.option_id,surface,enabled])
 return element
}
