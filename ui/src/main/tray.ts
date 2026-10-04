// The tray icon shows the session mode; the tray menu sets it.
import { Menu, Tray } from 'electron'
import type { SessionMode } from '../shared/protocol'
import { SESSION_MODES } from '../shared/protocol'
import { describeCore, describeGameflow, MODE_LABELS, type ShellState } from '../shared/state'
import { trayIcon } from './icons'

export interface TrayActions {
  setMode(mode: SessionMode): void
  showStatus(): void
  restartCore(): void
  quit(): void
}

export class CoachTray {
  private readonly tray: Tray

  constructor(private readonly actions: TrayActions) {
    this.tray = new Tray(trayIcon(null))
    this.tray.on('click', () => actions.showStatus())
  }

  update(state: ShellState): void {
    const connected = state.core === 'running' && state.mode !== null
    const gameflow = describeGameflow(state)
    const mode = state.mode ? MODE_LABELS[state.mode] : 'unknown'
    this.tray.setImage(trayIcon(connected ? state.mode : null))
    this.tray.setToolTip(`TFT Assistant\nMode: ${mode}\n${gameflow}`)
    this.tray.setContextMenu(
      Menu.buildFromTemplate([
        { label: describeCore(state.core), enabled: false },
        { label: `Gameflow: ${gameflow}`, enabled: false },
        { type: 'separator' },
        { label: 'Session mode', enabled: false },
        ...SESSION_MODES.map((m) => ({
          label: MODE_LABELS[m],
          type: 'radio' as const,
          checked: state.mode === m,
          enabled: connected,
          click: () => this.actions.setMode(m),
        })),
        { type: 'separator' },
        { label: 'Show status', click: () => this.actions.showStatus() },
        { label: 'Restart core', visible: state.core === 'stopped', click: () => this.actions.restartCore() },
        { label: 'Quit', click: () => this.actions.quit() },
      ]),
    )
  }
}
