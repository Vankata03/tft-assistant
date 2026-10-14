import { describe, expect, it } from 'vitest'
import { parseCoreMessage } from '../src/shared/protocol'
import { describeGameflow, type ShellState } from '../src/shared/state'

describe('parseCoreMessage', () => {
  it('accepts a gameflow message of the current version', () => {
    const raw = '{"v": 1, "type": "gameflow", "client_running": true, "phase": "InProgress"}'
    expect(parseCoreMessage(raw)).toEqual({ v: 1, type: 'gameflow', client_running: true, phase: 'InProgress' })
  })

  it.each([
    '{"v": 2, "type": "gameflow", "client_running": true, "phase": "Lobby"}',
    '{"type": "gameflow", "client_running": true, "phase": "Lobby"}',
    '{"v": 1, "type": "snapshot"}',
    'not json',
    'null',
  ])('rejects %s', (raw) => expect(parseCoreMessage(raw)).toBeNull())
})

describe('describeGameflow', () => {
  const running = (gameflow: ShellState['gameflow']): ShellState => ({ core: 'running', gameflow, mode: 'silent' })

  it.each<[ShellState, string]>([
    [{ core: 'starting', gameflow: null, mode: null }, 'Unknown (core not connected)'],
    [running({ clientRunning: false, phase: null }), 'League client not running'],
    [running({ clientRunning: true, phase: 'None' }), 'No phase (client idle)'],
    [running({ clientRunning: true, phase: 'InProgress' }), 'InProgress'],
  ])('%j reads %s', (state, text) => expect(describeGameflow(state)).toBe(text))
})

it('rejects a silent surface payload containing game content', () => {
  expect(parseCoreMessage(JSON.stringify({v:1,type:'baseline_state',mode:'silent',status:'logging',stale:[],content:{guides:[]},voice:null}))).toBeNull()
})

it('accepts empty Live status and rejects Live content in another mode', () => {
  expect(parseCoreMessage(JSON.stringify({v:1,type:'live_state',mode:'live',status:'waiting',revision:null,content:null,pin:null}))).not.toBeNull()
  expect(parseCoreMessage(JSON.stringify({v:1,type:'live_state',mode:'silent',status:'logging',revision:'invalid',content:{game_id:'secret'},pin:null}))).toBeNull()
  expect(parseCoreMessage('{"v":1,"type":"gameflow","client_running":"yes","phase":{}}')).toBeNull()
})
it('rejects malformed source deadlines and qualification booleans before rendering',()=>{
 const content={game_id:'123',snapshot_id:'frame',captured_at:'2026-10-14T12:00:00Z',evaluated_at:'2026-10-14T12:00:00Z',round_id:'3-2',phase:'planning',evidence_id:'sha256:'+('a'.repeat(64)),plan:{},advice:[],lines:[],projection:[],fits:[],opponents:[],entity_names:{},warnings:[],confidence_medium_min:.5,roster_valid_until:null,ownership_valid_until:null}
 const state={v:1,type:'live_state',mode:'live',status:'ready',revision:'sha256:'+('b'.repeat(64)),content,pin:null,invalidated:{},roster_qualified:true,ownership_qualified:true}
 expect(parseCoreMessage(JSON.stringify(state))).not.toBeNull()
 expect(parseCoreMessage(JSON.stringify({...state,content:{...content,captured_at:'not a clock'}}))).toBeNull()
 expect(parseCoreMessage(JSON.stringify({...state,roster_qualified:'true'}))).toBeNull()
 expect(parseCoreMessage(JSON.stringify({...state,content:{...content,ownership_valid_until:'2026-10-14'}}))).toBeNull()
})
