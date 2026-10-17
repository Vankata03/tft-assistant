// @vitest-environment jsdom
import {afterEach,it,expect,vi} from 'vitest'
import {act,createElement} from 'react'
import {createRoot} from 'react-dom/client'
import {LiveOverlay} from '../src/live/LiveOverlay'
import fixture from './fixtures/live.json'
import type {LiveState} from '../src/shared/messages'
import type {ShellState} from '../src/shared/state'

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true})
const now=Date.parse(fixture.content.captured_at)
const point={available:true,reason:null,comp_id:'A',line_id:'fixed',pinned:true,planning_round:'3-2',planning_snapshot_id:'123:3-2:0',round_id:'4-1',level:6,gold_floor:null,evidence_path:['plan','line']}
const view={...fixture,observed_phase:"combat",content:{...fixture.content,phase:"combat",next_planning:point,opponents:[],roll_tracker:null,confidence_medium_min:.5,entity_names:{},warnings:[]}} as unknown as LiveState
const state:ShellState={core:'running',mode:'live',gameflow:{clientRunning:true,phase:'InProgress'},availableModes:['silent','baseline','live'],live:view,overlayGeometry:{bounds:{x:0,y:0,width:1920,height:1080},anchors:[{kind:'line',index:0,x:.4,y:.8,width:.1,height:.03}],reason:null,displayId:1}}
let root:ReturnType<typeof createRoot>|null=null
let target:Element|null=null
let callback:IntersectionObserverCallback|undefined
let rect={x:0,y:0,left:0,top:0,right:300,bottom:100,width:300,height:100,toJSON:()=>({})}
function mount(changes:Partial<LiveState>={},mode:ShellState['mode']='live'){
 vi.useFakeTimers({toFake:['Date','setTimeout','clearTimeout','setInterval','clearInterval','requestAnimationFrame','cancelAnimationFrame']})
 vi.setSystemTime(now)
 Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'})
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(()=>rect)
 vi.stubGlobal('IntersectionObserver',class {constructor(cb:IntersectionObserverCallback){callback=cb}observe(node:Element){target=node}disconnect(){}})
 Object.assign(window,{coach:{liveShown:vi.fn(),livePreviewShown:vi.fn()}})
 const container=document.createElement('div');document.body.append(container);root=createRoot(container)
 act(()=>root!.render(createElement(LiveOverlay,{state:{...state,mode,live:{...view,...changes}},onPin:()=>{},now})))
 return container
}
afterEach(()=>{act(()=>root?.unmount());root=null;document.body.replaceChildren();vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers();rect={...rect,top:0,bottom:100}})


function intersect(){act(()=>callback?.([{target,isIntersecting:true,intersectionRatio:1}] as IntersectionObserverEntry[],{} as IntersectionObserver))}
it('acknowledges visible preview once after paint with original provenance',()=>{
 mount();intersect();act(()=>vi.advanceTimersToNextFrame())
 expect(window.coach.livePreviewShown).toHaveBeenCalledExactlyOnceWith({game_id:view.content!.game_id,revision:view.revision,data_snapshot_id:view.content!.data_snapshot_id,round_id:view.content!.round_id,preview:point,surface:'overlay',timestamp:new Date().toISOString()})
 intersect();act(()=>vi.advanceTimersToNextFrame());expect(window.coach.livePreviewShown).toHaveBeenCalledTimes(1)
 expect(window.coach.liveShown).not.toHaveBeenCalled()
})
it('rechecks hidden window and offscreen geometry at paint',()=>{
 mount();intersect();Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'})
 act(()=>vi.advanceTimersToNextFrame());expect(window.coach.livePreviewShown).not.toHaveBeenCalled()
 Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'})
 intersect();rect={...rect,top:900,bottom:1000};act(()=>vi.advanceTimersToNextFrame())
 expect(window.coach.livePreviewShown).not.toHaveBeenCalled()
})
it.each(['silent','baseline'] as const)('suppresses %s receipt',mode=>{
 mount({},mode);intersect();act(()=>vi.advanceTimersToNextFrame());expect(window.coach.livePreviewShown).not.toHaveBeenCalled()
})
it('does not report a paused preview',()=>{
 mount({next_planning_invalidated:'round or game changed'});intersect();act(()=>vi.advanceTimersToNextFrame());expect(window.coach.livePreviewShown).not.toHaveBeenCalled()
})

it('does not report an unavailable preview',()=>{
 mount({content:{...view.content!,next_planning:{...point,available:false,reason:'No qualified plan',comp_id:null,line_id:null,planning_round:null,planning_snapshot_id:null,round_id:null,level:null,pinned:false}}})
 intersect();act(()=>vi.advanceTimersToNextFrame());expect(window.coach.livePreviewShown).not.toHaveBeenCalled()
})
