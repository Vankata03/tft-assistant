// Status window: a placeholder for the second screen. Shows the core, the
// gameflow phase and the session mode, and sets the mode.
import { useEffect, useState } from 'react'
import type { SessionMode } from '../../shared/protocol'
import { canSelectMode, describeCore, describeGameflow, INITIAL_STATE, MODE_LABELS, type ShellState } from '../../shared/state'

const styles = {
  body: { fontFamily: 'system-ui, sans-serif', margin: 16, fontSize: 14 },
  row: { display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #ddd' },
  label: { color: '#666' },
} as const

export function App(): React.JSX.Element {
  const [state, setState] = useState<ShellState>(INITIAL_STATE)

  useEffect(() => {
    void window.coach.getState().then(setState)
    return window.coach.onState(setState)
  }, [])

  return (
    <main style={styles.body}>
      {state.error && <p role="alert">{state.error}</p>}
      <div style={styles.row}>
        <span style={styles.label}>Core</span>
        <span>{describeCore(state.core)}</span>
      </div>
      <div style={styles.row}>
        <span style={styles.label}>Gameflow phase</span>
        <strong data-testid="phase">{describeGameflow(state)}</strong>
      </div>
      <div style={styles.row}>
        <span style={styles.label}>Session mode</span>
        <SessionModeSelector state={state} onChange={(mode) => window.coach.setMode(mode)} />
      </div>
    </main>
  )
}

export function SessionModeSelector({ state, onChange }: { state: ShellState; onChange(mode: SessionMode): void }): React.JSX.Element {
  return (
    <select
      value={state.mode ?? ''}
      disabled={state.core !== 'running' || state.mode === null}
      onChange={(event) => {
        const mode = event.target.value as SessionMode
        if (canSelectMode(state, mode)) onChange(mode)
      }}
    >
      {state.mode === null && <option value="">unknown</option>}
      {(state.availableModes ?? []).map((mode) => (
        <option key={mode} value={mode} disabled={!canSelectMode(state, mode)}>
          {MODE_LABELS[mode]}
        </option>
      ))}
    </select>
  )
}
