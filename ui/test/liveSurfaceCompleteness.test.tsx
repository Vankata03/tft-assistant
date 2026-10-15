import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {expect,it} from 'vitest'
import {LiveCockpit} from '../src/live/LiveCockpit'
import {LiveOverlay} from '../src/live/LiveOverlay'
import type {LiveState} from '../src/shared/messages'
import type {ShellState} from '../src/shared/state'
import {parseCoreMessage} from '../src/shared/protocol'
import fixture from './fixtures/live.json'

const live=parseCoreMessage(JSON.stringify(fixture)) as LiveState
const state:ShellState={core:'running',mode:'live',availableModes:['silent','baseline','live'],gameflow:{clientRunning:true,phase:'InProgress'},live}
const cockpit=(next:ShellState=state)=>renderToStaticMarkup(createElement(LiveCockpit,{state:next,onMode:()=>{},onPin:()=>{},onDetail:()=>{},now:Date.parse(live.content!.captured_at)}))

it('Live cockpit names each stale field and how long it has been unread',()=>{
 const html=cockpit({...state,baseline:{v:1,type:'baseline_state',mode:'live',status:'Capture OK',content:null,voice:null,stale:[{field:'gold',reason:'gold unread',age_seconds:12.4},{field:'shop',reason:'shop timestamp unread',age_seconds:null}]}})
 expect(html).toContain('Paused · gold unread · 12s')
 expect(html).toContain('Paused · shop timestamp unread')
})

it('Live Game plan shows candidates, commit status and a called pivot',()=>{
 const plan={...live.content!.plan,candidates:['A','B'],pivot_from:'B',pivot_to:'A',pivot_round:'3-2'}
 const html=cockpit({...state,live:{...live,content:{...live.content!,plan}}})
 expect(html).toContain('Candidates A, B')
 expect(html).toContain('committed · backup B')
 expect(html).toContain('Pivot B → A at 3-2')
})

it('Live Line projection lists every candidate schedule with its roll-down points',()=>{
 const html=cockpit()
 expect(html).toContain('Levels 3-1 → 5 · roll-downs 3-1 to 10 gold')
 expect(html).toContain('Levels 3-1 → 5, 3-2 → 5 · roll-downs 3-2 to 50 gold')
 expect(html).toContain('hit 100% · death 0%')
})

it('overlay Line chip turns amber and names the Line that beats the pin with its gain',()=>{
 const advice=live.content!.advice.map(row=>row.domain==='econ'?{...row,payload:{...row.payload,pinned:true,pin_alternative:'roll:now@30',pin_gap:.42}}:row)
 const overlayGeometry={bounds:{x:0,y:0,width:1920,height:1080},anchors:[{kind:'line' as const,index:0,x:.4,y:.8,width:.1,height:.03}],reason:null,displayId:1}
 const html=renderToStaticMarkup(createElement(LiveOverlay,{state:{...state,overlayGeometry,live:{...live,content:{...live.content!,advice}}},onPin:()=>{},now:Date.parse(live.content!.captured_at)}))
 expect(html).toContain('pin-warning')
 const chip=html.slice(html.indexOf('<button'),html.indexOf('</button>'))
 expect(chip).toContain('roll:now@30 better by 0.42')
})
