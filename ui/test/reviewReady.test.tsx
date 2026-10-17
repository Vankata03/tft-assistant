import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {it,expect} from 'vitest'
import {ReviewReadyNotice} from '../src/renderer/src/review/ReviewReadyNotice'
import {parseCoreMessage} from '../src/shared/protocol'
import type {ShellState} from '../src/shared/state'
const ready={v:1 as const,type:'review_ready' as const,game_id:'123',mode:'baseline' as const,report_id:'sha256:'+('a'.repeat(64)),evidence_id:'sha256:'+('a'.repeat(64)),job_id:'b'.repeat(64),notice_id:'c'.repeat(32),ended_at:'2026-10-14T08:00:00Z',ready_at:'2026-10-14T08:00:20Z',latency_seconds:20,late:false,displayed_at:null,display_late:null,display_latency_seconds:null}
const state:ShellState={core:'running',mode:'silent',gameflow:{clientRunning:true,phase:'EndOfGame'},reviewReady:ready}
it('review-ready notice follows finished mode and requires real calibrated overlay geometry',()=>{
 expect(parseCoreMessage(JSON.stringify(ready))).not.toBeNull()
 expect(parseCoreMessage(JSON.stringify({...ready,mode:'silent'}))).toBeNull()
 expect(renderToStaticMarkup(createElement(ReviewReadyNotice,{state}))).toContain('Review ready')
 expect(renderToStaticMarkup(createElement(ReviewReadyNotice,{state,overlay:true}))).toBe('')
 const projected={...state,overlayGeometry:{bounds:{x:100,y:100,width:1280,height:800},displayId:1,reason:null,anchors:[{kind:'review' as const,index:0,x:.3,y:.1,width:.4,height:.05}]}}
 expect(renderToStaticMarkup(createElement(ReviewReadyNotice,{state:projected,overlay:true}))).toContain('Review ready')
 expect(renderToStaticMarkup(createElement(ReviewReadyNotice,{state:{...state,core:'restarting'}}))).toBe('')
 expect(renderToStaticMarkup(createElement(ReviewReadyNotice,{state:{...state,gameflow:{clientRunning:true,phase:'InProgress'}}}))).toBe('')
})
