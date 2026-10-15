// @vitest-environment jsdom
import {afterEach,it,expect,vi} from 'vitest'
import {act,createElement} from 'react'
import {createRoot} from 'react-dom/client'
import {LiveCockpit} from '../src/live/LiveCockpit'
import fixture from './fixtures/live.json'
import type {LiveState} from '../src/shared/messages'
import type {ShellState} from '../src/shared/state'

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true})
const now=Date.parse(fixture.content.captured_at)
const view={...fixture,content:{...fixture.content,opponents:[],roll_tracker:null,confidence_medium_min:.5,entity_names:{},warnings:[]}} as unknown as LiveState
const state:ShellState={core:'running',mode:'live',gameflow:{clientRunning:true,phase:'InProgress'},availableModes:['silent','baseline','live'],live:view}
let root:ReturnType<typeof createRoot>|null=null
let target:Element|null=null
let callback:IntersectionObserverCallback|undefined
let rect={x:0,y:0,left:0,top:0,right:300,bottom:100,width:300,height:100,toJSON:()=>({})}
function mount(){
 vi.useFakeTimers({toFake:['Date','setTimeout','clearTimeout','setInterval','clearInterval','requestAnimationFrame','cancelAnimationFrame']})
 vi.setSystemTime(now)
 Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'})
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(()=>rect)
 vi.stubGlobal('IntersectionObserver',class {constructor(cb:IntersectionObserverCallback){callback=cb}observe(node:Element){target=node}disconnect(){}})
 Object.assign(window,{coach:{liveShown:vi.fn()}})
 const container=document.createElement('div');document.body.append(container);root=createRoot(container)
 act(()=>root!.render(createElement(LiveCockpit,{state,onMode:()=>{},onPin:()=>{},onDetail:()=>{}})))
 return container
}
afterEach(()=>{act(()=>root?.unmount());root=null;document.body.replaceChildren();vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers();rect={...rect,top:0,bottom:100}})

it('expires unchanged rendered advice and pin controls without another publication',()=>{
 const container=mount()
 expect(container.textContent).toContain('Hold econ')
 act(()=>vi.advanceTimersByTime(2500))
 expect(container.textContent).toContain('required evidence expired')
 const pins=[...container.querySelectorAll('button')].filter(button=>button.textContent==='Pin Line')
 expect(pins.length).toBeGreaterThan(0)
 expect(pins.every(button=>button.disabled)).toBe(true)
})

it('rechecks visibility fraction and deadline at the actual paint acknowledgement',()=>{
 mount()
 const entry=(fraction:number)=>[{target,isIntersecting:true,intersectionRatio:fraction}] as unknown as IntersectionObserverEntry[]
 act(()=>callback!(entry(.2),{} as IntersectionObserver))
 document.dispatchEvent(new Event('visibilitychange'))
 act(()=>vi.advanceTimersToNextFrame())
 expect(window.coach.liveShown).not.toHaveBeenCalled()
 act(()=>callback!(entry(.8),{} as IntersectionObserver))
 rect={...rect,top:900,bottom:1000}
 act(()=>vi.advanceTimersToNextFrame())
 expect(window.coach.liveShown).not.toHaveBeenCalled()
 rect={...rect,top:0,bottom:100}
 act(()=>callback!(entry(.8),{} as IntersectionObserver))
 act(()=>vi.advanceTimersToNextFrame())
 expect(window.coach.liveShown).toHaveBeenCalledTimes(1)
})


it('expanded scored comparisons retain distinct Line identities',()=>{
 const container=mount()
 const compare=[...container.querySelectorAll('button')].find(button=>button.textContent?.startsWith('Compare'))!
 act(()=>compare.click())
 const items=[...container.querySelectorAll('.live-options li')]
 expect(items.length).toBe(view.content!.advice[0]!.options.length)
 for(const option of view.content!.advice[0]!.options)expect(items.some(item=>item.textContent?.includes(option.option_id))).toBe(true)
 expect(new Set(items.map(item=>item.querySelector('strong')?.textContent)).size).toBe(items.length)
})
