// Runtime side of the generated message types in ./messages.ts.
import type { CoreMessage, SessionMode, UiMessage } from './messages'

export type { CoreMessage, SessionMode, UiMessage }

/** Fails to compile when the core's schema version changes and the types are regenerated. */
export const SCHEMA_VERSION: CoreMessage['v'] & UiMessage['v'] = 1

export const SESSION_MODES: readonly SessionMode[] = [
  'silent',
  'baseline',
  'live',
]

const CORE_MESSAGE_TYPES: Record<CoreMessage['type'], true> = {
  gameflow: true,
  session_mode: true,
  error: true,
  baseline_state: true,
  live_state: true,
  evidence_page: true,
  surface_geometry: true,
  review_response:true,
  review_games:true,
  review_ready:true,
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function finiteJson(value: unknown, depth = 0): boolean {
  if (depth > 64) return false
  if (typeof value === 'number') return Number.isFinite(value)
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return true
  if (Array.isArray(value)) return value.every((item) => finiteJson(item, depth + 1))
  return object(value) && Object.values(value).every((item) => finiteJson(item, depth + 1))
}

const PHASES = ['planning','roll_down','augment','carousel','combat','end','unknown']
const hash = (value: unknown): boolean => typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value)

const awareDate = (value:unknown):boolean=>typeof value==='string'&&/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)&&Number.isFinite(Date.parse(value))

function liveContent(value: unknown): boolean {
  if (!object(value) || !finiteJson(value)) return false
  if (!['game_id','snapshot_id','captured_at','evaluated_at','round_id'].every((key) => typeof value[key] === 'string')) return false
  if(!awareDate(value.captured_at)||!awareDate(value.evaluated_at)||['roster_valid_until','ownership_valid_until'].some(key=>value[key]!==undefined&&value[key]!==null&&!awareDate(value[key])))return false
  if (!PHASES.includes(value.phase as string) || !hash(value.evidence_id) || !object(value.plan)) return false
  if (!['advice','lines','projection','fits'].every((key) => Array.isArray(value[key]))) return false
  return (value.advice as unknown[]).every((row) => object(row) &&
    ['decision_id','option_id','domain','action','reason'].every((key) => typeof row[key] === 'string') &&
    ['act_this_phase','soon','information'].includes(row.urgency as string) &&
    typeof row.confidence === 'number' && row.confidence >= 0 && row.confidence <= 1 &&
    (row.valid_until===null||awareDate(row.valid_until)) &&
    object(row.payload) && object(row.numbers) && Array.isArray(row.options) && Array.isArray(row.evidence_path))
}

/** Parse a message from the core; null for another schema version or an unknown type. */
export function parseCoreMessage(raw: string): CoreMessage | null {
  if (raw.length > 256 * 1024 || new TextEncoder().encode(raw).length > 256 * 1024) return null
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof data !== 'object' || data === null) return null
  const { v, type } = data as { v?: unknown; type?: unknown }
  if (
    v !== SCHEMA_VERSION ||
    typeof type !== 'string' ||
    !Object.hasOwn(CORE_MESSAGE_TYPES, type)
  )
    return null
  const message = data as Record<string, unknown>
  if (!finiteJson(data)) return null
  if (type === 'gameflow' && (typeof message.client_running !== 'boolean' || (message.phase !== null && typeof message.phase !== 'string'))) return null
  if (type === 'error' && (typeof message.code !== 'string' || typeof message.message !== 'string')) return null
  if (type === 'session_mode' && (!SESSION_MODES.includes(message.mode as SessionMode) || !Array.isArray(message.available_modes) || !message.available_modes.every((mode) => SESSION_MODES.includes(mode as SessionMode)))) return null
  if (type === 'live_state') {
    if (!SESSION_MODES.includes(message.mode as SessionMode) || typeof message.status !== 'string') return null
    if (message.mode !== 'live' && (message.content !== null || message.pin !== null)) return null
    if (message.content !== null && (!hash(message.revision) || !liveContent(message.content))) return null
    if(['roster_qualified','ownership_qualified'].some(key=>message[key]!==undefined&&message[key]!==null&&typeof message[key]!=='boolean'))return null
    if(message.invalidated!==undefined&&(!object(message.invalidated)||!Object.values(message.invalidated).every(value=>typeof value==='string')))return null
    const pin = message.pin
    if (pin !== null && (!object(pin) || !['comp_id','line_id','seed'].every((key) => typeof pin[key] === 'string'))) return null
  }
  if(type==='review_ready'&&(!['baseline','live'].includes(message.mode as string)||typeof message.game_id!=='string'||!/^\d{1,30}$/.test(message.game_id)||!hash(message.report_id)||!hash(message.evidence_id)||!['ended_at','ready_at'].every(key=>typeof message[key]==='string'&&Number.isFinite(Date.parse(message[key] as string)))||typeof message.latency_seconds!=='number'||message.latency_seconds<0||typeof message.late!=='boolean'))return null
  if(type==='review_games'&&(typeof message.request_id!=='string'||!Array.isArray(message.games)||!message.games.every(game=>object(game)&&typeof game.game_id==='string'&&typeof game.review_locked==='boolean'&&typeof game.finished==='boolean')))return null
  if(type==='review_response'&&(typeof message.request_id!=='string'||typeof message.game_id!=='string'||!['summary','page','what_if','tag','media','regenerate'].includes(message.operation as string)||!object(message.value)))return null
  if (type === 'evidence_page' && (typeof message.request_id !== 'string' || typeof message.game_id !== 'string' || !hash(message.revision) || !object(message.page) || !Array.isArray(message.page.items))) return null
  if (type === 'surface_geometry') {
    if (!SESSION_MODES.includes(message.mode as SessionMode) || typeof message.status !== 'string' || !Array.isArray(message.anchors)) return null
    if (message.mode === 'silent' && (message.geometry !== null || message.anchors.length)) return null
    if (message.geometry !== null && (!object(message.geometry) || message.geometry.coordinate_space !== 'physical_pixels' || !object(message.geometry.client_bounds) || typeof message.geometry.read_at !== 'string' || !object(message.geometry.calibration))) return null
    if (message.mode === 'baseline' && message.anchors.some((anchor) => !object(anchor) || !['shop','level','par','augment','carousel','wisp','review'].includes(anchor.kind as string))) return null
  }
  if (type === 'baseline_state') {
    const state = data as Record<string, unknown>
    if (
      !SESSION_MODES.includes(state.mode as SessionMode) ||
      typeof state.status !== 'string' ||
      !Array.isArray(state.stale)
    )
      return null
    if (
      state.mode !== 'baseline' &&
      (state.content !== null || state.voice !== null)
    )
      return null
    if (state.content !== null) {
      if (typeof state.content !== 'object' || state.content === null)
        return null
      const content = state.content as Record<string, unknown>
      if (
        typeof content.patch !== 'string' ||
        typeof content.snapshot_id !== 'string'
      )
        return null
      if (
        ![
          'guides',
          'shop',
          'recipes',
          'augments',
          'wisps',
          'faced',
          'warnings',
        ].every((key) => Array.isArray(content[key]))
      )
        return null
    }
  }
  return data as CoreMessage
}
