// @vitest-environment jsdom
import {act,createElement} from 'react'
import {createRoot} from 'react-dom/client'
import {it,expect,vi} from 'vitest'
import {ReviewMoment} from '../src/renderer/src/review/ReviewMoment'
import {ReviewPanel} from '../src/renderer/src/review/ReviewPanel'
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true})
it('loads only authenticated scored option headers and uses what-if without simulation',async()=>{
 const calls:unknown[]=[]
 const request=vi.fn(async(operation:string,args:Record<string,unknown>)=>{
  calls.push([operation,args])
  const path=args.path as (string|number)[]|undefined
  if(operation==='what_if')return {option_id:'hold',expected_placement:4.2,standard_error:.3,simulation:'already_scored'}
  if(path?.join('/')==='moments/2/evidence_path')return {kind:'array',items:[{value:'evidence'},{value:'replay'},{value:'contexts'},{value:7},{value:'evaluation'},{value:'advice'},{value:0}],next_cursor:null}
  if(path?.at(-1)==='options')return {items:[{path:[...path,0],reference:true},{path:[...path,1],reference:true}],next_cursor:null}
  const id=path?.at(-1)===0?'buy':'hold'
  return {items:[{path:[...path!,'option_id'],value:id},{path:[...path!,'action'],value:id},{path:[...path!,'expected_placement'],value:id==='buy'?3.1:4.2},{path:[...path!,'standard_error'],value:.3}],next_cursor:null}
 })
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host)
 try{
  await act(async()=>root.render(createElement(ReviewMoment,{moment:{moment_id:'m',moment_path:['moments',2],round_id:'3-2',category:'shop',engine_choice:{option_id:'buy',action:'buy',expected_placement:3.1,standard_error:.2},player_choice:{option_id:'hold',action:'hold',expected_placement:4.2,standard_error:.3}},request,onDebug:()=>{}})))
  expect(host.textContent).toContain('Engine choice')
  await act(async()=>{[...host.querySelectorAll('button')].find(b=>b.textContent==='Load scored options')!.click()})
  const select=host.querySelector('select')!;expect([...select.options].map(o=>o.value)).toEqual(['buy','hold'])
  await act(async()=>{select.value='hold';select.dispatchEvent(new Event('change',{bubbles:true}))})
  expect(host.textContent).toContain('4.20 ± 0.30')
  expect(host.textContent).toContain('Already scored')
  expect(calls).toContainEqual(['what_if',{moment_id:'m',option_id:'hold'}])
  expect(calls.some(call=>JSON.stringify(call).includes('rollouts'))).toBe(false)
 }finally{act(()=>root.unmount());host.remove()}
})
it('loads a logged keyframe through protected media chunks and releases its object URL',async()=>{
 const create=vi.fn(()=> 'blob:protected-keyframe'),revoke=vi.fn()
 Object.assign(URL,{createObjectURL:create,revokeObjectURL:revoke})
 const request=vi.fn(async(operation:string,args:Record<string,unknown>)=>{
  expect(operation).toBe('media');expect(args.name).toBe('media/'+'a'.repeat(32)+'.webp')
  return {name:args.name,offset:0,total_bytes:4,next_cursor:null,content_type:'image/webp',base64:'UklGRg=='}
 })
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host)
 try{
  await act(async()=>root.render(createElement(ReviewMoment,{moment:{moment_id:'m',round_id:'3-2',category:'shop',keyframe:{media_name:'media/'+'a'.repeat(32)+'.webp',timestamp:'2026-10-13T12:00:00+00:00',logged_reason:'choice_change'}},request,onDebug:()=>{}})))
  await act(async()=>{[...host.querySelectorAll('button')].find(b=>b.textContent==='View logged keyframe')!.click()})
  expect(host.querySelector('img')?.src).toBe('blob:protected-keyframe')
  expect(host.textContent).toContain('choice change')
  expect(create).toHaveBeenCalledTimes(1)
 }finally{act(()=>root.unmount());host.remove()}
 expect(revoke).toHaveBeenCalledWith('blob:protected-keyframe')
})

it('changing the selected game hides prior private review while a locked summary is pending',async()=>{
 let release:(value:unknown)=>void=()=>{}
 Object.assign(window,{coach:{reviewGames:async()=>({games:[{game_id:'123',finished:true,mode:'baseline',review_locked:false,placement:4},{game_id:'124',finished:true,mode:'silent',review_locked:true,placement:null}]}),requestReview:async(args:Record<string,unknown>)=>args.game_id==='123'?{value:{game_id:'123',locked:false,report_id:'old',evidence_id:'old',top5:[{moment_id:'m',round_id:'3-2',category:'PRIVATE_OLD_GAME',cost:-1.1,shown:{status:'shown'}}]}}:new Promise(resolve=>{release=resolve})}})
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host)
 try{
  await act(async()=>root.render(createElement(ReviewPanel,{state:{core:'running',mode:'baseline',gameflow:{clientRunning:true,phase:'Lobby'}}})))
  await act(async()=>{host.querySelector('button')!.click()})
  await act(async()=>{[...host.querySelectorAll('button')].find(b=>b.textContent?.startsWith('123'))!.click()})
  expect(host.textContent).toContain('PRIVATE_OLD_GAME')
  act(()=>{[...host.querySelectorAll('button')].find(b=>b.textContent?.startsWith('124'))!.click()})
  expect(host.textContent).not.toContain('PRIVATE_OLD_GAME')
  await act(async()=>{release({value:{game_id:'124',locked:true,top5:[]}})})
  expect(host.textContent).toContain('Review locked')
 }finally{act(()=>root.unmount());host.remove()}
})
it('opening a finished-game review replaces the inactive cockpit with a compact status',async()=>{
 const {App}=await import('../src/renderer/src/App')
 const finished={core:'running',mode:'baseline',gameflow:{clientRunning:true,phase:'EndOfGame'},baseline:{v:1,type:'baseline_state',mode:'baseline',status:'Synthetic finished game',content:null,voice:null,stale:[]}}
 Object.assign(window,{coach:{getState:async()=>finished,onState:()=>()=>{},reviewGames:async()=>({games:[]})}})
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host)
 try{
  await act(async()=>root.render(createElement(App)))
  expect(host.querySelector('.cockpit')).not.toBeNull()
  await act(async()=>{[...host.querySelectorAll('button')].find(b=>b.textContent==='Post-game review')!.click()})
  expect(host.querySelector('.cockpit')).toBeNull()
  expect(host.textContent).toContain('Synthetic finished game')
  expect(host.textContent).toContain('Logged games')
  await act(async()=>{[...host.querySelectorAll('button')].find(b=>b.textContent==='Close review')!.click()})
  expect(host.querySelector('.cockpit')).not.toBeNull()
 }finally{act(()=>root.unmount());host.remove()}
})
