// What the shell knows, shared by the main process, the tray and the windows.
import type { SessionMode } from './protocol'

/** starting: spawned, not ready · running: connected · restarting: waiting to respawn · stopped: gave up. */
export type CoreStatus = 'starting' | 'running' | 'restarting' | 'stopped'

export interface GameflowState {
  clientRunning: boolean
  phase: string | null
}

export interface ShellState {
  core: CoreStatus
  /** Null while the core is not connected. */
  gameflow: GameflowState | null
  /** Null while the core is not connected. */
  mode: SessionMode | null
}

export const INITIAL_STATE: ShellState = { core: 'starting', gameflow: null, mode: null }

export function describeGameflow(state: ShellState): string {
  if (state.core !== 'running' || state.gameflow === null) return 'Unknown (core not connected)'
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
