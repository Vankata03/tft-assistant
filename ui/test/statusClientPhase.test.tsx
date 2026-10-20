// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest'
import {act,createElement} from 'react'
import {createRoot} from 'react-dom/client'
import {App} from '../src/renderer/src/App'
import type {BaselineState} from '../src/shared/messages'
import type {ShellState} from '../src/shared/state'

Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true})
// The actual smoke-test status: settings are missing, so capture reports its error.
const missingSettings:BaselineState={type:'baseline_state',v:1,mode:'baseline',content:null,stale:[],voice:null,
  status:'Capture settings unavailable: settings.toml not found'}
const base:ShellState={core:'running',mode:'baseline',availableModes:['silent','baseline'],
  gameflow:{clientRunning:true,phase:'Lobby'},baseline:missingSettings}
let root:ReturnType<typeof createRoot>|null=null
let publish:(state:ShellState)=>void=()=>{}

function mount(state:ShellState){
  Object.assign(window,{coach:{
    getState:()=>Promise.resolve(state),
    onState:(listener:(next:ShellState)=>void)=>{publish=listener;return ()=>{}},
  }})
  const container=document.createElement('div');document.body.append(container)
  root=createRoot(container)
  act(()=>root!.render(createElement(App)))
  act(()=>publish(state))
}
const phase=()=>document.querySelector('[data-testid="client-phase"]')?.textContent

afterEach(()=>{act(()=>root?.unmount());root=null;document.body.innerHTML='';Reflect.deleteProperty(window,'coach')})

it('shows the client phase in the status window despite missing capture settings, and follows changes', ()=>{
  mount(base)
  expect(document.body.textContent).toContain('Capture settings unavailable')
  expect(phase()).toBe('Client: Lobby')
  act(()=>publish({...base,gameflow:{clientRunning:true,phase:'ChampSelect'}}))
  expect(phase()).toBe('Client: ChampSelect')
  act(()=>publish({...base,gameflow:{clientRunning:true,phase:null}}))
  expect(phase()).toBe('Client: No phase (client idle)')
  act(()=>publish({...base,gameflow:{clientRunning:false,phase:null}}))
  expect(phase()).toBe('Client: League client not running')
})

it('reports the phase as status in Silent mode without game content', ()=>{
  mount({...base,mode:'silent',baseline:{...missingSettings,mode:'silent'},gameflow:{clientRunning:true,phase:'InProgress'}})
  expect(phase()).toBe('Client: InProgress')
  expect(document.body.textContent).toContain('Silent game')
})
