// @vitest-environment jsdom
import {afterEach,it,expect,vi} from 'vitest'
import {act,createElement} from 'react'
import {createRoot} from 'react-dom/client'
import {ReviewReadyNotice} from '../src/renderer/src/review/ReviewReadyNotice'
import type {ShellState} from '../src/shared/state'
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true})
const ready={v:1 as const,type:'review_ready' as const,game_id:'123',mode:'baseline' as const,report_id:'sha256:'+('a'.repeat(64)),evidence_id:'sha256:'+('a'.repeat(64)),job_id:'b'.repeat(64),notice_id:'c'.repeat(32),ended_at:'2026-10-17T00:00:00Z',ready_at:'2026-10-17T00:00:20Z',latency_seconds:20,late:false,displayed_at:null,display_late:null,display_latency_seconds:null}
const state:ShellState={core:'running',mode:'silent',gameflow:{clientRunning:true,phase:'EndOfGame'},reviewReady:ready}
let root:ReturnType<typeof createRoot>|null=null
let callback:IntersectionObserverCallback|undefined,target:Element|null=null
function mount(changes:Partial<ShellState>={}){
 vi.useFakeTimers();vi.setSystemTime(Date.parse('2026-10-17T00:00:35Z'))
 Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'})
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockReturnValue({left:0,top:0,right:300,bottom:100,width:300,height:100} as DOMRect)
 vi.stubGlobal('IntersectionObserver',class{constructor(cb:IntersectionObserverCallback){callback=cb}observe(node:Element){target=node}disconnect(){}})
 Object.assign(window,{coach:{reviewNoticeShown:vi.fn()}})
 const container=document.createElement('div');document.body.append(container);root=createRoot(container)
 act(()=>root!.render(createElement(ReviewReadyNotice,{state:{...state,...changes}})))
 return container
}
function paint(){act(()=>callback?.([{target,isIntersecting:true,intersectionRatio:1}] as IntersectionObserverEntry[],{} as IntersectionObserver));act(()=>vi.advanceTimersToNextFrame())}
afterEach(()=>{act(()=>root?.unmount());root=null;callback=undefined;target=null;document.body.replaceChildren();vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers()})
it('acknowledges a visible finished-game notice at display time independently of idle mode',()=>{
 const container=mount();paint()
 expect(window.coach.reviewNoticeShown).toHaveBeenCalledExactlyOnceWith({game_id:ready.game_id,report_id:ready.report_id,evidence_id:ready.evidence_id,job_id:ready.job_id,notice_id:ready.notice_id,surface:'status',timestamp:new Date().toISOString()})
 paint();expect(window.coach.reviewNoticeShown).toHaveBeenCalledTimes(1)
 expect(container.textContent).toContain('late')
})
it('rechecks document visibility at the animation frame',()=>{
 mount();act(()=>callback?.([{target,isIntersecting:true,intersectionRatio:1}] as IntersectionObserverEntry[],{} as IntersectionObserver))
 Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'})
 act(()=>vi.advanceTimersToNextFrame());expect(window.coach.reviewNoticeShown).not.toHaveBeenCalled()
})
it.each([{core:'restarting' as const},{reviewReady:null},{gameflow:{clientRunning:true,phase:'InProgress'}}])('suppresses unavailable notices',changes=>{
 mount(changes);paint();expect(window.coach.reviewNoticeShown).not.toHaveBeenCalled()
})

it('suppresses offscreen notices and cancels stale pending frames',()=>{
 mount();vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockReturnValue({left:2000,top:0,right:2300,bottom:100,width:300,height:100} as DOMRect)
 paint();expect(window.coach.reviewNoticeShown).not.toHaveBeenCalled()
 act(()=>root!.render(createElement(ReviewReadyNotice,{state:{...state,reviewReady:null}})))
 paint();expect(window.coach.reviewNoticeShown).not.toHaveBeenCalled()
})


it('waits for ancestor opacity restoration without another intersection event',async()=>{
 const container=mount();container.style.opacity='0';paint()
 expect(window.coach.reviewNoticeShown).not.toHaveBeenCalled()
 await act(async()=>{container.style.opacity='1';await Promise.resolve()})
 expect(window.coach.reviewNoticeShown).not.toHaveBeenCalled()
 act(()=>vi.advanceTimersToNextFrame())
 expect(window.coach.reviewNoticeShown).toHaveBeenCalledTimes(1)
 paint();expect(window.coach.reviewNoticeShown).toHaveBeenCalledTimes(1)
})


it.each(['opacity','display','visibility','contentVisibility'] as const)('rechecks ancestor %s at the visible frame',property=>{
 const container=mount()
 act(()=>callback?.([{target,isIntersecting:true,intersectionRatio:1}] as IntersectionObserverEntry[],{} as IntersectionObserver))
 container.style[property]=({opacity:'0',display:'none',visibility:'hidden',contentVisibility:'hidden'})[property]
 act(()=>vi.advanceTimersToNextFrame())
 expect(window.coach.reviewNoticeShown).not.toHaveBeenCalled()
 container.style[property]=''
 act(()=>vi.advanceTimersToNextFrame())
 expect(window.coach.reviewNoticeShown).toHaveBeenCalledTimes(1)
})

it('cancels ancestor visibility retries when the notice is removed',()=>{
 const container=mount();container.style.opacity='0';paint()
 act(()=>root!.render(createElement(ReviewReadyNotice,{state:{...state,reviewReady:null}})))
 container.style.opacity='1'
 act(()=>vi.advanceTimersToNextFrame())
 expect(window.coach.reviewNoticeShown).not.toHaveBeenCalled()
})
