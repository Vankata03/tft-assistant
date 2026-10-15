// @vitest-environment jsdom
import {act,createElement} from 'react'
import {createRoot} from 'react-dom/client'
import {afterEach,expect,it,vi} from 'vitest'
import {ReviewPanel} from '../src/renderer/src/review/ReviewPanel'
import type {ReviewRequest} from '../src/renderer/src/review/ReviewMoment'
import type {ReviewSectionProps} from '../src/renderer/src/review/ReviewSection'
import type {RequestReview} from '../src/shared/messages'
import type {ShellState} from '../src/shared/state'
import {pager} from './fixtures/reviewPager'

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true})
// The existing moment request stays assignable to the narrower section request.
const assignable:(request:ReviewRequest)=>ReviewSectionProps['request']=request=>request
void assignable

const report_id=`sha256:${'1'.repeat(64)}`,evidence_id=`sha256:${'2'.repeat(64)}`
const timeline=Array.from({length:9},(_,index)=>({moment_id:`m${index}`,engine_decision_id:`econ:${index}`,log_seq:index,round_id:`3-${index}`,category:'econ',cost:-.1,paired_uncertainty:.05,close_call:false,differed:true,shown:{status:'unavailable',reason:'display_attribution_unavailable'},reason:'line_projection',unavailable:{},evidence_path:['evidence','replay','records',index]}))
const graph={surface:{timeline,lines:[],plan_timeline:[],fights:[],positioning:[]},evidence:{replay:{records:timeline.map(row=>({raw_member:row.moment_id}))}},debug:{gap_events:[]}}
const pages=pager(graph)
let calls:Omit<RequestReview,'v'|'type'|'request_id'>[]=[]
let root:ReturnType<typeof createRoot>|null=null
afterEach(()=>{act(()=>root?.unmount());root=null;document.body.replaceChildren();vi.unstubAllGlobals()})

function mount(){
 calls=[]
 Object.assign(window,{coach:{
  reviewGames:vi.fn(async()=>({type:'review_games',v:1,request_id:'g',games:[{game_id:'123',finished:true,review_locked:false,mode:'live',placement:4}]})),
  requestReview:vi.fn(async(message:Omit<RequestReview,'v'|'type'|'request_id'>)=>{
   calls.push(message)
   const value=message.operation==='summary'?{game_id:'123',locked:false,report_id,evidence_id,top5:[],placement:{value:4},follow_rate:{value:null,reason:'not_shown'},category_costs:{},section_paths:{timeline:['surface','timeline'],debug:['debug']}}
    :await pages('page',{path:message.path,cursor:message.cursor,limit:message.limit})
   return {type:'review_response',v:1,request_id:'r',game_id:'123',operation:message.operation,value}
  }),
 }})
 const host=document.createElement('div');document.body.append(host);root=createRoot(host)
 return host
}
const state=(mode:ShellState['mode']):ShellState=>({core:'running',mode,availableModes:['silent','baseline','live'],gameflow:{clientRunning:true,phase:'EndOfGame'},reviewRequest:{game_id:'123',serial:1}})
const click=async(host:HTMLElement,text:string)=>{const button=[...host.querySelectorAll('button')].find(node=>node.textContent===text);expect(button,text).toBeTruthy();await act(async()=>button!.click())}

it('opens normal sections only through typed surface pages and keeps their pages across parent rerenders',async()=>{
 const host=mount()
 await act(async()=>root!.render(createElement(ReviewPanel,{state:state('live'),onOpenChange:()=>{}})))
 await click(host,'Full round timeline')
 const pages=calls.filter(call=>call.operation!=='summary')
 expect(pages[0]).toMatchObject({operation:'page',path:['surface','timeline'],report_id,evidence_id,cursor:0,limit:8})
 expect(pages.every(call=>call.operation==='page'&&call.path[0]==='surface'&&call.path[1]==='timeline')).toBe(true)
 expect(host.querySelectorAll('[aria-label="timeline review"] article').length).toBe(8)
 expect(host.querySelector('pre')).toBeNull()
 await click(host,'Load more')
 expect(host.querySelectorAll('[aria-label="timeline review"] article').length).toBe(9)
 const before=calls.length
 await act(async()=>root!.render(createElement(ReviewPanel,{state:{...state('live')},onOpenChange:()=>{}})))
 expect(host.querySelectorAll('[aria-label="timeline review"] article').length).toBe(9)
 expect(calls.length).toBe(before)
})

it('discards loaded section pages when the session mode changes',async()=>{
 const host=mount()
 await act(async()=>root!.render(createElement(ReviewPanel,{state:state('live')})))
 await click(host,'Full round timeline')
 await click(host,'Load more')
 await act(async()=>root!.render(createElement(ReviewPanel,{state:state('baseline')})))
 expect(host.querySelectorAll('[aria-label="timeline review"] article').length).toBe(8)
 expect(calls.filter(call=>call.operation==='page'&&call.cursor===0&&call.path.join()==='surface,timeline').length).toBe(2)
})

it('shows raw recorded evidence only after an explicit Debug action',async()=>{
 const host=mount()
 await act(async()=>root!.render(createElement(ReviewPanel,{state:state('live')})))
 await click(host,'Full round timeline')
 const debug=[...host.querySelectorAll('button')].filter(node=>node.textContent==='Debug evidence')[0]!
 await act(async()=>debug.click())
 expect(calls.at(-1)?.path).toEqual(['evidence','replay','records',0])
 expect(host.textContent).toContain('raw_member')
 await click(host,'Debug')
 expect(calls.at(-1)?.path).toEqual(['debug'])
})
