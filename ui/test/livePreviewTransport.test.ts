import {expect,it,vi} from 'vitest'
import type {CoachApi} from '../src/preload'
import {CoreLink} from '../src/main/coreLink'
import fixture from './fixtures/live.json'

const native=vi.hoisted(()=>({coach:null as CoachApi|null,send:vi.fn()}))
vi.mock('electron',()=>({contextBridge:{exposeInMainWorld:(_name:string,api:CoachApi)=>{native.coach=api}},ipcRenderer:{send:native.send}}))

it('preload emits a separate preview IPC channel and CoreLink serializes its typed receipt',async()=>{
 const sent:string[]=[]
 class Socket extends EventTarget {
  static OPEN=1
  readyState=1
  constructor(_url:string){super();queueMicrotask(()=>this.dispatchEvent(new Event('open')))}
  send(value:string){sent.push(value)}
  close(){}
 }
 vi.stubGlobal('WebSocket',Socket)
 const link=new CoreLink()
 try{
  await import('../src/preload/index')
  link.connect(12345,'token');await Promise.resolve()
  const message={game_id:'123',revision:fixture.revision,data_snapshot_id:fixture.content.data_snapshot_id,
   round_id:'3-2',preview:{available:true,reason:null,comp_id:'A',line_id:'fixed',pinned:true,
    planning_round:'3-2',planning_snapshot_id:'123:3-2:0',round_id:'4-1',level:6,gold_floor:null,
    evidence_path:['plan','line']},surface:'overlay' as const,timestamp:'2026-10-17T00:00:00Z'}
  native.coach!.livePreviewShown(message)
  expect(native.send).toHaveBeenCalledExactlyOnceWith('live-preview-shown',message)
  link.livePreviewShown(message)
  expect(sent.map(value=>JSON.parse(value))).toEqual([{v:1,type:'hello',token:'token'},{v:1,type:'live_preview_shown',...message}])
 }finally{link.close();vi.unstubAllGlobals()}
})
