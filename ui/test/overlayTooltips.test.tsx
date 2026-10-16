// @vitest-environment jsdom
import {readFileSync} from 'node:fs'
import {act,createElement} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach,expect,it,vi} from 'vitest'
import type {ShellState} from '../src/shared/state'
import fixture from './fixtures/live.json'

vi.hoisted(()=>{
 Object.assign(globalThis,{__LIVE_ENABLED__:true,IS_REACT_ACT_ENVIRONMENT:true})
 history.replaceState(null,'','/?surface=overlay')
})
import {App} from '../src/renderer/src/App'

const css=['../src/renderer/src/cockpit.css','../src/live/live.css'].map(path=>readFileSync(new URL(path,import.meta.url),'utf8')).join('\n')
const capturedAt=Date.parse(fixture.content.captured_at)
const TAG_HEIGHT=30

/** Fixture layout: each positioned element occupies its percentage anchor in a 1000x500 overlay. */
function layout(){
 Object.assign(window,{innerWidth:1000,innerHeight:500})
 vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){
  const percent=(value:string)=>value.endsWith('%')?Number.parseFloat(value)/100:0
  const left=percent(this.style.left)*1000,top=percent(this.style.top)*500
  const width=percent(this.style.width)*1000||40
  return {x:left,y:top,left,top,right:left+width,bottom:top+TAG_HEIGHT,width,height:TAG_HEIGHT,toJSON:()=>({})} as DOMRect
 })
}

let root:ReturnType<typeof createRoot>|null=null
async function mount(state:ShellState){
 vi.useFakeTimers({toFake:['Date','setTimeout','clearTimeout','setInterval','clearInterval']})
 vi.setSystemTime(capturedAt)
 layout()
 vi.stubGlobal('IntersectionObserver',class {observe(){}disconnect(){}})
 const coach={getState:async()=>state,onState:()=>()=>{},reportShown:vi.fn(),liveShown:vi.fn(),overlayInteractive:vi.fn()}
 Object.assign(window,{coach})
 const style=document.createElement('style');style.textContent=css;document.head.append(style)
 const host=document.createElement('div');document.body.append(host);root=createRoot(host)
 await import('../src/live/LiveShell')
 await act(async()=>{root!.render(createElement(App))})
 for(let tick=0;tick<3;tick++)await act(async()=>{await vi.advanceTimersByTimeAsync(0)})
 return {host,coach}
}
afterEach(()=>{act(()=>root?.unmount());root=null;document.head.replaceChildren();document.body.replaceChildren();vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers()})

function move(x:number,y:number){act(()=>{document.body.dispatchEvent(new MouseEvent('mousemove',{bubbles:true,clientX:x,clientY:y}))})}
function wait(ms:number){act(()=>{vi.advanceTimersByTime(ms)})}
function tooltipShown(tag:Element){return getComputedStyle(tag.querySelector('.overlay-tooltip')!).display!=='none'}
function tagWithText(host:Element,text:string){
 const tag=[...host.querySelectorAll('.overlay-tag')].find(node=>node.textContent?.includes(text))
 expect(tag,`tag containing ${text}`).toBeTruthy()
 return tag!
}

const baseline:ShellState={core:'running',mode:'baseline',availableModes:['silent','baseline'],gameflow:{clientRunning:true,phase:'InProgress'},
 baseline:{v:1,type:'baseline_state',mode:'baseline',status:'Capture OK',stale:[],voice:null,content:{
  patch:'fixture',snapshot_id:'fixture',round_id:'3-2',guides:[],selected:null,xp_hint:null,
  par:{probability:.54,paused:null,uncertain:false},
  shop:[{slot:1,entity:{id:'fixture',name:'Fixture carry',icon:'',cost:3},in_guide:true}],
  recipes:[],augments:[],wisps:[],faced:[],warnings:[],overlay_bounds:{x:0,y:0,width:1000,height:500},overlay_allowed:true,phase:'planning',
  anchors:[{kind:'shop',index:1,x:.2,y:.8,width:.1,height:.04},{kind:'par',index:0,x:.4,y:.1,width:.15,height:.04}]}}} as ShellState

it('shows a Baseline tag reason only after the pointer dwells on the tag for about 400 ms',async()=>{
 const {host}=await mount(baseline)
 const tag=tagWithText(host,'In Guide')
 expect(tooltipShown(tag)).toBe(false)
 move(250,410)
 wait(300)
 expect(tooltipShown(tag)).toBe(false)
 wait(150)
 expect(tooltipShown(tag)).toBe(true)
})

it('cancels a pending tooltip when the pointer leaves the tag or the overlay, and hides an open one on leave',async()=>{
 const {host}=await mount(baseline)
 const tag=tagWithText(host,'In Guide')
 move(250,410);wait(300)
 move(600,250);wait(400)
 expect(tooltipShown(tag)).toBe(false)
 move(250,410);wait(300)
 act(()=>{document.body.dispatchEvent(new MouseEvent('mouseout',{bubbles:true,relatedTarget:null}))})
 wait(400)
 expect(tooltipShown(tag)).toBe(false)
 move(250,410);wait(400)
 expect(tooltipShown(tag)).toBe(true)
 move(600,250)
 expect(tooltipShown(tag)).toBe(false)
})

it('places the open tooltip above its tag rather than over it',async()=>{
 const {host}=await mount(baseline)
 const tag=tagWithText(host,'54%')
 move(450,60);wait(400)
 const tooltip=getComputedStyle(tag.querySelector('.overlay-tooltip')!)
 expect(tooltip.display).toBe('block')
 expect(tooltip.position).toBe('absolute')
 expect(tooltip.top).toBe('auto')
 expect(tooltip.bottom).toMatch(/^calc\(100% \+ [1-9]\d*px\)$/)
 expect(getComputedStyle(tag).position).toBe('absolute')
})

const econ=fixture.content.advice.find(row=>row.domain==='econ')!
const buy={...econ,decision_id:'shop-buy',domain:'shop',action:'Buy',reason:'completes_guide_pair',confidence:1,payload:{buys:[{slot:0,unit_id:'c'}]}}
const live:ShellState={core:'running',mode:'live',availableModes:['silent','baseline','live'],gameflow:{clientRunning:true,phase:'InProgress'},
 live:{...fixture,content:{...fixture.content,confidence_medium_min:.5,entity_names:{c:'Fixture carry'},opponents:[],roll_tracker:null,advice:[{...econ,confidence:1},buy]}} as unknown as ShellState['live'],
 overlayGeometry:{bounds:{x:0,y:0,width:1000,height:500},displayId:1,reason:null,anchors:[
  {kind:'shop',index:0,x:.2,y:.8,width:.1,height:.05},{kind:'line',index:0,x:.6,y:.5,width:.1,height:.05}]}} as unknown as ShellState

it('reveals an ordinary Live advice reason on dwell without ever requesting window input',async()=>{
 const {host,coach}=await mount(live)
 const tag=tagWithText(host,'Buy Fixture carry')
 expect(getComputedStyle(tag).pointerEvents).toBe('none')
 move(250,410);wait(300)
 expect(tooltipShown(tag)).toBe(false)
 wait(150)
 expect(tooltipShown(tag)).toBe(true)
 expect(tag.querySelector('.overlay-tooltip')!.textContent).toBe('completes guide pair')
 act(()=>{tag.dispatchEvent(new MouseEvent('mouseover',{bubbles:true,relatedTarget:document.body}));(tag as HTMLElement).click()})
 expect(coach.overlayInteractive).not.toHaveBeenCalled()
})

it('keeps the Line widget as the only Live tag that toggles window input, and gives it the same dwell tooltip',async()=>{
 const {host,coach}=await mount(live)
 const tag=tagWithText(host,'guide:A')
 const widget=tag.querySelector('.line-widget')!
 expect(getComputedStyle(widget).pointerEvents).toBe('auto')
 act(()=>{widget.dispatchEvent(new MouseEvent('mouseover',{bubbles:true,relatedTarget:document.body}))})
 expect(coach.overlayInteractive.mock.calls).toEqual([[true]])
 move(650,260);wait(400)
 expect(tooltipShown(tag)).toBe(true)
 act(()=>{widget.dispatchEvent(new MouseEvent('mouseout',{bubbles:true,relatedTarget:document.body}))})
 expect(coach.overlayInteractive.mock.calls).toEqual([[true],[false]])
})

it('leaves Baseline tags click-through and lets only the finished review toast request window input',async()=>{
 const {host,coach}=await mount(baseline)
 const tag=tagWithText(host,'In Guide')
 expect(getComputedStyle(tag).pointerEvents).toBe('none')
 move(250,410);wait(400)
 expect(tooltipShown(tag)).toBe(true)
 act(()=>{tag.dispatchEvent(new MouseEvent('mouseover',{bubbles:true,relatedTarget:document.body}));(tag as HTMLElement).click()})
 expect(coach.overlayInteractive).not.toHaveBeenCalled()
 act(()=>root!.unmount());root=null;document.body.replaceChildren()
 const finished={...baseline,gameflow:{clientRunning:true,phase:'EndOfGame'},
  reviewReady:{v:1,type:'review_ready',game_id:'123',mode:'baseline',report_id:'sha256:'+'a'.repeat(64),evidence_id:'sha256:'+'a'.repeat(64),ended_at:'2026-10-07T00:00:00Z',ready_at:'2026-10-07T00:00:20Z',latency_seconds:20,late:false},
  overlayGeometry:{bounds:{x:0,y:0,width:1000,height:500},displayId:1,reason:null,anchors:[{kind:'review',index:0,x:.4,y:.4,width:.2,height:.05}]}} as unknown as ShellState
 const second=await mount(finished)
 const toast=second.host.querySelector('.review-ready-toast')!
 act(()=>{toast.dispatchEvent(new MouseEvent('mouseover',{bubbles:true,relatedTarget:document.body}))})
 expect(second.coach.overlayInteractive.mock.calls).toEqual([[true]])
})
