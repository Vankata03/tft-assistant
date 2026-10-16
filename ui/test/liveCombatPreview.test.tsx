import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {expect,it} from 'vitest'
import {LiveOverlay} from '../src/live/LiveOverlay'
import type {LiveNextPlanningPreview,LiveState} from '../src/shared/messages'
import type {ShellState} from '../src/shared/state'
import {parseCoreMessage} from '../src/shared/protocol'
import fixture from './fixtures/live.json'

const live=parseCoreMessage(JSON.stringify(fixture)) as LiveState
const now=Date.parse(live.content!.captured_at)
const overlayGeometry={bounds:{x:0,y:0,width:1920,height:1080},anchors:[{kind:'line' as const,index:0,x:.4,y:.8,width:.1,height:.03},{kind:'xp' as const,index:0,x:.3,y:.8,width:.1,height:.03}],reason:null,displayId:1}
const point:LiveNextPlanningPreview={available:true,reason:null,comp_id:'A',line_id:'fixed',pinned:true,planning_round:'3-2',planning_snapshot_id:'g:3-2:0',round_id:'4-1',level:6,gold_floor:null,evidence_path:['plan','line']}
const unavailable:LiveNextPlanningPreview={available:false,reason:"No qualified plan from this round's planning phase",comp_id:null,line_id:null,pinned:false,planning_round:null,planning_snapshot_id:null,round_id:null,level:null,gold_floor:null,evidence_path:['plan','line']}
function overlay(next_planning:LiveNextPlanningPreview|null,changes:Partial<LiveState>={},mode:ShellState['mode']='live'):string{
 const view:LiveState={...live,observed_phase:'combat',...changes,content:{...live.content!,phase:'combat',next_planning}}
 const state:ShellState={core:'running',mode,availableModes:['silent','baseline','live'],gameflow:{clientRunning:true,phase:'InProgress'},live:view,overlayGeometry}
 return renderToStaticMarkup(createElement(LiveOverlay,{state,onPin:()=>{},now}))??''
}

it('combat shows one chip previewing the next scheduled point of the qualified plan',()=>{
 const html=overlay(point)
 expect(html.match(/class="overlay-tag/g)).toHaveLength(1)
 expect(html).toContain('Next planning · fixed · level 6 at 4-1')
 expect(html).toContain('planned in 3-2 · pinned Line')
 expect(overlay({...point,level:5,gold_floor:10,round_id:'3-1',pinned:false})).toContain('Next planning · fixed · level 5, roll to 10 gold at 3-1')
})

it('combat does not reinterpret the current-phase Line or Level-now rows as combat calls',()=>{
 const html=overlay(point)
 expect(html).not.toContain('<button')
 expect(html).not.toContain('Level now')
 expect(html).not.toContain('line-widget')
})

it('combat without a qualified or current preview shows an explicit paused state',()=>{
 expect(overlay(unavailable)).toContain('paused · No qualified plan from this round')
 expect(overlay(null)).toContain('paused · next planning call unavailable')
 const expired=overlay(point,{next_planning_invalidated:'round or game changed'})
 expect(expired).toContain('paused · round or game changed')
 expect(expired).not.toContain('level 6 at 4-1')
})

it('the preview leaves with combat and never shows outside Live mode',()=>{
 expect(overlay(point,{observed_phase:'planning'})).not.toContain('Next planning')
 expect(overlay(point,{},'baseline')).toBe('')
 expect(overlay(point,{},'silent')).toBe('')
})
