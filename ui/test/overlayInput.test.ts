import {afterEach,expect,it,vi} from 'vitest'
import type {ShellState} from '../src/shared/state'
import type {SurfaceGeometryState} from '../src/shared/messages'
import fixture from './fixtures/live.json'

const native=vi.hoisted(()=>({windows:[] as {visible:boolean;ignoreMouseEvents:boolean;webContents:{on:()=>void;send:()=>void}}[]}))
vi.mock('electron',()=>({
 BrowserWindow:class {
  visible=false
  ignoreMouseEvents=true
  webContents={on:()=>{},send:()=>{}}
  constructor(){native.windows.push(this)}
  setIgnoreMouseEvents(value:boolean){this.ignoreMouseEvents=value}
  setContentProtection(){}
  on(){}
  loadURL(){return Promise.resolve()}
  loadFile(){return Promise.resolve()}
  setBounds(){}
  showInactive(){this.visible=true}
  hide(){this.visible=false}
  isVisible(){return this.visible}
  close(){this.visible=false}
 },
 screen:{getAllDisplays:()=>[{id:1,bounds:{x:0,y:0,width:1920,height:1080}}],
  screenToDipRect:(_window:unknown,rectangle:unknown)=>rectangle,
  dipToScreenRect:(_window:unknown,rectangle:unknown)=>rectangle},
}))
import {CoachOverlay} from '../src/main/overlayWindow'

const originalPlatform=Object.getOwnPropertyDescriptor(process,'platform')!
afterEach(()=>{Object.defineProperty(process,'platform',originalPlatform);vi.useRealTimers();native.windows.length=0})

it.each(['silent','geometry','disconnect','toggle'])('restores click-through after hiding an interactive overlay: %s',(cause)=>{
 vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-15T08:00:00Z'))
 Object.defineProperty(process,'platform',{value:'win32',configurable:true})
 const at=new Date().toISOString()
 const geometry:SurfaceGeometryState={v:1,type:'surface_geometry',mode:'live',status:'external native fixture',
  geometry:{window_id:'positive-window',coordinate_space:'physical_pixels',client_bounds:{x:0,y:0,width:1920,height:1080},read_at:at,source:'Win32-client-rectangle',layout_read_at:at,layout_source_sha256:'b'.repeat(64),window_mode:'borderless',ui_scale:1,profile_sha256:'a'.repeat(64),calibration:{client_size:[1920,1080],ui_scale:1}},
  anchors:[{kind:'line',index:0,x:.2,y:.2,width:.1,height:.05}]}
 const state:ShellState={core:'running',mode:'live',gameflow:{clientRunning:true,phase:'InProgress'},
  live:fixture as unknown as ShellState['live'],surfaceGeometry:geometry}
 const overlay=new CoachOverlay()
 try{
  overlay.update(state)
  const window=native.windows[0]!
  expect(window.visible).toBe(true)
  overlay.setInteractive(window.webContents as never,true)
  expect(window.ignoreMouseEvents).toBe(false)
  if(cause==='silent')overlay.update({...state,mode:'silent',surfaceGeometry:{...geometry,mode:'silent'}})
  else if(cause==='geometry')overlay.update({...state,surfaceGeometry:{...geometry,geometry:null}})
  else if(cause==='disconnect')overlay.update({...state,core:'restarting'})
  else overlay.toggle()
  expect(window.visible).toBe(false)
  expect(window.ignoreMouseEvents).toBe(true)
  if(cause==='toggle')overlay.toggle()
  else overlay.update(state)
  expect(window.visible).toBe(true)
  expect(window.ignoreMouseEvents).toBe(true)
  overlay.setInteractive(window.webContents as never,true)
  expect(window.ignoreMouseEvents).toBe(false)
  overlay.update({...state,mode:'baseline',surfaceGeometry:{...geometry,mode:'baseline'},baseline:{mode:'baseline',content:{}} as ShellState['baseline']})
  expect(window.visible).toBe(true)
  expect(window.ignoreMouseEvents).toBe(true)
  overlay.setInteractive(window.webContents as never,true)
  expect(window.ignoreMouseEvents).toBe(true)
 }finally{overlay.close()}
})
