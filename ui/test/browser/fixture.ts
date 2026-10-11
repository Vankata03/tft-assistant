/** External preload fixture for exercising the actual renderer; never bundled by Electron. */
import type {
  BaselineContent,
  EntityDisplay,
  GuideDisplay,
} from '../../src/shared/messages'
import type { ShellState } from '../../src/shared/state'
import { canSelectMode } from '../../src/shared/state'

const unit = (id: string, name: string, cost = 3): EntityDisplay => ({
  id,
  name,
  cost,
  icon: '',
})
const carry = unit('carry', 'Fixture carry'),
  tank = unit('tank', 'Fixture tank', 2),
  support = unit('support', 'Fixture support', 1)
const sword = unit('sword', 'Fixture sword', 0),
  bow = unit('bow', 'Fixture bow', 0),
  blade = unit('blade', 'Fixture blade', 0)
const guide: GuideDisplay = {
  id: 'guide-a',
  name: 'Guide A',
  tier: 'S',
  units: [carry, tank, support],
  early_layout: [
    { entity: tank, position: null },
    { entity: support, position: null },
  ],
  final_layout: [
    { entity: carry, position: 23 },
    { entity: tank, position: 2 },
    { entity: support, position: 17 },
  ],
  stage_tips: {
    '3': 'Fixture stage plan · preserve the Guide carry.',
    '4': 'Fixture next-stage plan.',
  },
  stage_plan: [{ round: '3-4', level: 7 }],
  carousel: [sword, bow],
  alternatives: ['guide-b'],
}
const guideB: GuideDisplay = {
  ...guide,
  id: 'guide-b',
  name: 'Guide B',
  tier: 'A',
  alternatives: ['guide-a'],
}
const content: BaselineContent = {
  patch: 'fixture-patch',
  snapshot_id: 'fixture-static-snapshot',
  round_id: '3-2',
  phase: 'planning',
  guides: [guide, guideB],
  selected: null,
  xp_hint: {
    target_level: 7,
    target_round: '3-4',
    buys: 2,
    gold: 8,
    passive_xp: 4,
    text: 'Guide: 7 at 3-4 · 2 XP buys (8 gold) short',
  },
  par: { probability: 0.54, paused: null, uncertain: false },
  shop: [{ slot: 1, entity: carry, in_guide: true }],
  recipes: [
    {
      unit: carry,
      item: blade,
      components: [
        { entity: sword, held: true },
        { entity: bow, held: false },
      ],
    },
  ],
  augments: [
    {
      entity: unit('aug-a', 'Fixture augment A', 0),
      tier: 'S',
      global_tier: 'A',
      in_guide: true,
      offered: true,
      offer_index: 0,
    },
    {
      entity: unit('aug-b', 'Fixture augment B', 0),
      tier: 'B',
      global_tier: 'B',
      in_guide: false,
      offered: false,
      offer_index: null,
    },
  ],
  wisps: [
    {
      entity: unit('wisp', 'Fixture Wisp', 0),
      worth: 3.5,
      worth_label: null,
      worth_stage: null,
      paired_standard_error: null,
      source: 'owner',
      offered_slot: 4,
    },
  ],
  faced: [{ name: 'Fixture rival', result: 'win' }],
  warnings: ['Synthetic renderer fixture; no production qualification.'],
  anchors: [
    { kind: 'shop', index: 1, x: 0.22, y: 0.83, width: 0.12, height: 0.04 },
    { kind: 'par', index: 0, x: 0.72, y: 0.07, width: 0.2, height: 0.05 },
    { kind: 'wisp', index: 4, x: 0.8, y: 0.83, width: 0.14, height: 0.04 },
  ],
  overlay_bounds: { x: 0, y: 0, width: 1280, height: 800 },
  overlay_allowed: true,
}
let state: ShellState = {
  core: 'running',
  mode: 'baseline',
  gameflow: { clientRunning: true, phase: 'InProgress' },
  availableModes: ['silent', 'baseline'],
  error: null,
  baseline: {
    v: 1,
    type: 'baseline_state',
    mode: 'baseline',
    status: 'Capture OK',
    stale: [],
    content,
    voice: null,
  },
}
const listeners = new Set<(state: ShellState) => void>()
const shown: { surface: string; id: string; timestamp: string }[] = []
const reports = document.createElement('output')
function publish(): void {
  for (const listener of listeners) listener(structuredClone(state))
}
window.coach = {
  reportShown: (surface, id, timestamp) => {
    shown.push({ surface, id, timestamp })
    reports.textContent = `Shown events: ${shown.length} · voice: ${shown.filter((row) => row.surface === 'voice').length}`
  },
  getState: async () => structuredClone(state),
  onState: (listener) => {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  setMode: (mode) => {
    if (!canSelectMode(state, mode)) return
    state = {
      ...state,
      mode,
      baseline: {
        v: 1,
        type: 'baseline_state',
        mode,
        status: 'Capture OK',
        stale: [],
        content: mode === 'baseline' ? content : null,
        voice: null,
      },
    }
    publish()
  },
  selectGuide: (id) => {
    if (state.mode !== 'baseline') return
    const selected = id === 'guide-a' ? guide : id === 'guide-b' ? guideB : null
    if (!selected) return
    state = {
      ...state,
      baseline: {
        ...state.baseline!,
        content: { ...content, selected },
        voice: null,
      },
    }
    publish()
  },
}
const fixture = {
  reset() {
    state = {
      ...state,
      mode: 'baseline',
      gameflow: { clientRunning: true, phase: 'Lobby' },
      baseline: {
        v: 1,
        type: 'baseline_state',
        mode: 'baseline',
        status: 'Capture OK',
        stale: [],
        content: { ...content, selected: guide },
        voice: null,
      },
    }
    publish()
  },
  stale() {
    state = {
      ...state,
      baseline: {
        ...state.baseline!,
        stale: [{ field: 'board', age_seconds: 8, reason: 'board unread' }],
        content:
          state.mode === 'baseline'
            ? {
                ...content,
                selected: guide,
                par: {
                  probability: null,
                  paused: 'own board unread',
                  uncertain: false,
                },
              }
            : null,
      },
    }
    publish()
  },
  stage() {
    state = {
      ...state,
      baseline: {
        ...state.baseline!,
        content:
          state.mode === 'baseline'
            ? { ...content, selected: guide, round_id: '4-1' }
            : null,
        voice:
          state.mode === 'baseline'
            ? {
                id: 'fixture:baseline-stage:4',
                text: 'Fixture next-stage plan.',
              }
            : null,
      },
    }
    publish()
  },
  phase(phase: BaselineContent['phase']) {
    state = {
      ...state,
      baseline: {
        ...state.baseline!,
        content:
          state.mode === 'baseline'
            ? { ...content, selected: guide, phase }
            : null,
      },
    }
    publish()
  },
  restart() {
    state = { ...state, core: 'restarting', baseline: null }
    publish()
  },
  reconnect() {
    state = {
      ...state,
      core: 'running',
      baseline: {
        v: 1,
        type: 'baseline_state',
        mode: state.mode ?? 'silent',
        status: 'Capture OK',
        stale: [],
        content:
          state.mode === 'baseline' ? { ...content, selected: guide } : null,
        voice: null,
      },
    }
    publish()
  },
  unavailable() {
    state = {
      ...state,
      baseline: {
        v: 1,
        type: 'baseline_state',
        mode: state.mode ?? 'silent',
        status: 'Fresh source rejected; validated patch data unavailable',
        stale: [],
        content: null,
        voice: null,
      },
    }
    publish()
  },
}
Object.assign(window, { rendererFixture: fixture })
const controls = document.createElement('div')
controls.style.cssText =
  'display:flex;flex-wrap:wrap;gap:8px;padding:8px;background:#382c14;position:relative;z-index:1000;'
for (const [label, action] of [
  ['Baseline lobby', fixture.reset],
  ['Unread board', fixture.stale],
  ['Disconnect', fixture.restart],
  ['Reconnect', fixture.reconnect],
  ['Data unavailable', fixture.unavailable],
  ['Stage start', fixture.stage],
] as const) {
  const button = document.createElement('button')
  button.textContent = label
  button.addEventListener('click', action)
  controls.append(button)
}
reports.textContent = 'Shown events: 0 · voice: 0'
controls.append(reports)
document.querySelector('#root')!.before(controls)
void import('../../src/renderer/src/main')
