// Status window: a placeholder for the second screen. Shows the core, the
// gameflow phase and the session mode, and sets the mode.
import { useEffect, useState } from 'react'
import { SESSION_MODES } from '../../shared/protocol'
import { describeCore, describeGameflow, INITIAL_STATE, MODE_LABELS, type ShellState } from '../../shared/state'

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

  const connected = state.core === 'running' && state.mode !== null

  return (
    <main style={styles.body}>
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
        <select
          value={state.mode ?? ''}
          disabled={!connected}
          onChange={(event) => window.coach.setMode(event.target.value as (typeof SESSION_MODES)[number])}
        >
          {state.mode === null && <option value="">unknown</option>}
          {SESSION_MODES.map((mode) => (
            <option key={mode} value={mode}>
              {MODE_LABELS[mode]}
            </option>
          ))}
        </select>
      </div>
    </main>
  )
}
