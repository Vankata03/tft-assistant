import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {expect,it} from 'vitest'
import {LiveCockpit} from '../src/live/LiveCockpit'
import type {LiveState} from '../src/shared/messages'
import type {ShellState} from '../src/shared/state'
import fixture from './fixtures/live.json'
import {parseCoreMessage} from '../src/shared/protocol'

const live = parseCoreMessage(JSON.stringify(fixture)) as LiveState
const state: ShellState = {core:'running', mode:'live', availableModes:['silent','baseline','live'], gameflow:{clientRunning:true,phase:'InProgress'}, live}
const props = {state, onMode:()=>{}, onPin:()=>{}, onDetail:()=>{}, now:Date.parse(live.content!.captured_at)}

it('Live cockpit retains Engine rank and presents all simultaneous planning surfaces',()=>{
 const html=renderToStaticMarkup(createElement(LiveCockpit,props))
 expect(html).toContain('Game plan')
 expect(html).toContain('Line projection')
 expect(html).toContain('Target layout')
 expect(html).toContain('Opponents')
 let previous=-1
 for(const row of live.content!.advice){
  const index=html.indexOf(`data-decision="${row.decision_id}"`)
  expect(index).toBeGreaterThan(previous)
  previous=index
 }
 expect(html).toContain('Pin Line')
 expect(html).toContain('Complete own ownership')
})

it.each(['silent','baseline'] as const)('Live renderer never leaks content in %s',mode=>{
 const html=renderToStaticMarkup(createElement(LiveCockpit,{...props,state:{...state,mode}}))
 expect(html).not.toContain('Hold econ')
 expect(html).not.toContain('Line projection')
})
it('shows low-confidence evidence and the observed capture failure status in Live',()=>{
 const weak={...live,content:{...live.content!,advice:live.content!.advice.map(row=>({...row,confidence:.2})),confidence_medium_min:.5}}
 const html=renderToStaticMarkup(createElement(LiveCockpit,{...props,state:{...state,live:weak,baseline:{v:1,type:'baseline_state',mode:'live',status:'Exclusive fullscreen · overlay off; use windowed or borderless.',content:null,voice:null,stale:[]}}}))
 expect(html).toContain('Low confidence · ?')
 expect(html).toContain('Exclusive fullscreen · overlay off')
 expect(html).toContain('confidence-low')
})
