// @vitest-environment jsdom
import {act,createElement} from 'react'
import {createRoot} from 'react-dom/client'
import {it,expect,vi} from 'vitest'
import {ReviewSection} from '../src/renderer/src/review/ReviewSection'
Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true})
it('renders protected typed Line charts and observed values without raw rollout evidence',async()=>{
 const projection={round_id:'3-3',gold:42,level:6,hp:59,hit_probability:.7,expected_placement:3.1,planned_gold:30}
 const row={round_id:'3-2',log_seq:7,observed:{gold:35,level:5,hp:60},recommended:{line_id:'guide:A',expected_placement:3.1,standard_error:.2,schedule:{levels:{'3-3':6},rolls:{'3-3':30}},projections:[projection]},actual:{line_id:'fitted-hold',expected_placement:4.2,standard_error:.3,schedule:{levels:{},rolls:{}},projections:[{...projection,gold:50,hp:40}]},pin:null,unavailable:{},evidence_path:['lines',0]}
 const request=vi.fn(async(_operation:string,args:Record<string,unknown>)=>args.path?.toString()==='surface,lines'?{kind:'array',path:['surface','lines'],items:[{path:['surface','lines',0],reference:true}],total:1,next_cursor:null}:{kind:'object',path:['surface','lines',0],items:Object.entries(row).map(([key,value])=>({path:['surface','lines',0,key],value})),total:8,next_cursor:null})
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host)
 try{
  await act(async()=>root.render(createElement(ReviewSection,{name:'lines',path:['surface','lines'],request,onDebug:()=>{}})))
  expect(host.textContent).toContain('Engine forecast')
  expect(host.textContent).toContain('Fitted player policy · ex-post')
  expect(host.textContent).toContain('Observed · gold 35')
  expect(host.textContent).toContain('guide:A')
  expect(host.textContent).toContain('59')
  expect(host.querySelectorAll('svg').length).toBe(2)
  expect(host.querySelector('pre')).toBeNull()
  expect(request.mock.calls.every(([,args])=>JSON.stringify(args.path).includes('surface'))).toBe(true)
 }finally{act(()=>root.unmount());host.remove()}
})
