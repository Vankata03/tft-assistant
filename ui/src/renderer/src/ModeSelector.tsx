import type { SessionMode } from '../../shared/protocol'
import { canSelectMode, MODE_LABELS, type ShellState } from '../../shared/state'

export function SessionModeSelector({
  state,
  onChange,
}: {
  state: ShellState
  onChange(mode: SessionMode): void
}): React.JSX.Element {
  return (
    <select
      aria-label="Session mode"
      value={state.mode ?? ''}
      disabled={state.core !== 'running' || state.mode === null}
      onChange={(event) => {
        const mode = event.target.value as SessionMode
        if (canSelectMode(state, mode)) onChange(mode)
      }}
    >
      {state.mode === null ? <option value="">Unknown mode</option> : null}
      {(state.availableModes ?? []).map((mode) => (
        <option key={mode} value={mode} disabled={!canSelectMode(state, mode)}>
          {MODE_LABELS[mode]}
        </option>
      ))}
    </select>
  )
}
