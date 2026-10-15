import type { BaselineState, LiveState, SurfaceGeometryState, OverlayBounds,LiveSurfaceAnchor,ReviewReady } from './messages'
// What the shell knows, shared by the main process, the tray and the windows.
import type { SessionMode } from './protocol'

/** starting: spawned, not ready · running: connected · restarting: waiting to respawn · stopped: gave up. */
export type CoreStatus = 'starting' | 'running' | 'restarting' | 'stopped'

export interface GameflowState {
  clientRunning: boolean
  phase: string | null
}

declare global {const __LIVE_ENABLED__:boolean}

export interface ShellState {
  core: CoreStatus
  /** Null while the core is not connected. */
  gameflow: GameflowState | null
  /** Null while the core is not connected. */
  mode: SessionMode | null
  /** Authoritative modes supplied by the connected core; absent means unknown. */
  availableModes?: readonly SessionMode[]
  /** Latest actionable error reported by the core. */
  error?: string | null
  baseline?: BaselineState | null
  live?: LiveState | null
  reviewReady?:ReviewReady|null
  reviewRequest?:{game_id:string;serial:number}|null
  surfaceGeometry?: SurfaceGeometryState | null
  overlayGeometry?: {bounds:OverlayBounds|null;anchors:readonly LiveSurfaceAnchor[];reason:string|null;displayId:number|null} | null
}

export const INITIAL_STATE: ShellState = {
  core: 'starting',
  gameflow: null,
  mode: null,
  availableModes: [],
  error: null,
}

export function describeGameflow(state: ShellState): string {
  if (state.core !== 'running' || state.gameflow === null)
    return 'Unknown (core not connected)'
  if (!state.gameflow.clientRunning) return 'League client not running'
  const { phase } = state.gameflow
  return phase === null || phase === 'None' ? 'No phase (client idle)' : phase
}

export function describeCore(status: CoreStatus): string {
  return {
    starting: 'Core starting',
    running: 'Core running',
    restarting: 'Core restarting',
    stopped: 'Core stopped',
  }[status]
}

export const MODE_LABELS: Record<SessionMode, string> = {
  silent: 'Silent',
  baseline: 'Baseline',
  live: 'Live',
}

export function canSelectMode(state: ShellState, mode: SessionMode): boolean {
  if (
    state.core !== 'running' ||
    state.mode === null ||
    !state.availableModes?.includes(mode)
  )
    return false
  const inGame = ['InProgress', 'Reconnect', 'PreEndOfGame'].includes(
    state.gameflow?.phase ?? '',
  )
  const ranks = { silent: 0, baseline: 1, live: 2 }
  return !inGame || ranks[mode] <= ranks[state.mode]
}
