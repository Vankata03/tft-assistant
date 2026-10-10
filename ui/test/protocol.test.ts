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
