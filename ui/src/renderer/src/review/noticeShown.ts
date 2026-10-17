import {useEffect,useRef,useState} from 'react'
import type {ReviewReady} from '../../../shared/messages'

/** Browser visibility qualification; native compositor timing remains separate. */
export function useReviewNoticeShown(ready:ReviewReady|null|undefined,enabled:boolean,surface:'status'|'overlay'){
 const element=useRef<HTMLDivElement>(null)
 const [shown,setShown]=useState<{id:string;at:string}|null>(null)
 useEffect(()=>{
  const node=element.current
  if(!node||!ready||!enabled||typeof IntersectionObserver==='undefined')return
  let sent=false,frame=0,intersecting=false
  const visible=()=>{
   const b=node.getBoundingClientRect(),style=getComputedStyle(node)
   const intersection=Math.max(0,Math.min(b.right,innerWidth)-Math.max(b.left,0))*Math.max(0,Math.min(b.bottom,innerHeight)-Math.max(b.top,0))
   return intersecting&&document.visibilityState==='visible'&&node.isConnected&&b.width*b.height>0&&intersection/(b.width*b.height)>=.5&&style.display!=='none'&&style.visibility!=='hidden'&&style.opacity!=='0'
  }
  const check=()=>{
   if(sent||!visible())return
   cancelAnimationFrame(frame)
   frame=requestAnimationFrame(()=>{
    if(sent||!visible())return
    sent=true
    const timestamp=new Date().toISOString()
    setShown({id:ready.notice_id,at:timestamp})
    window.coach?.reviewNoticeShown({game_id:ready.game_id,report_id:ready.report_id,evidence_id:ready.evidence_id,job_id:ready.job_id,notice_id:ready.notice_id,surface,timestamp})
   })
  }
  const observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.target===node)intersecting=entry.isIntersecting&&entry.intersectionRatio>=.5;check()},{threshold:.5})
  observer.observe(node);document.addEventListener('visibilitychange',check)
  return()=>{observer.disconnect();cancelAnimationFrame(frame);document.removeEventListener('visibilitychange',check)}
 },[ready?.notice_id,enabled,surface])
 return {element,shownAt:shown?.id===ready?.notice_id?shown?.at:null}
}
