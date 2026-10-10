import { BrowserWindow } from 'electron'
import { join } from 'node:path'
import type { ShellState } from '../shared/state'

/** The Baseline overlay stays hidden until capture supplies bounds and calibrated anchors. */
export class CoachOverlay {
  private window: BrowserWindow | null = null
  private enabled = true
  private state: ShellState | null = null

  update(state: ShellState): void {
    this.state = state
    const content =
      state.core === 'running' &&
      state.mode === 'baseline' &&
      state.baseline?.mode === 'baseline'
        ? state.baseline.content
        : null
    const inGame = ['InProgress', 'Reconnect', 'PreEndOfGame'].includes(
      state.gameflow?.phase ?? '',
    )
    if (
      !inGame ||
      !this.enabled ||
      !content?.overlay_allowed ||
      !content.overlay_bounds ||
      !content.anchors.length
    ) {
      this.window?.hide()
      return
    }
    if (!this.window) {
      this.window = new BrowserWindow({
        show: false,
        frame: false,
        transparent: true,
        resizable: false,
        focusable: false,
        skipTaskbar: true,
        alwaysOnTop: true,
        webPreferences: {
          preload: join(__dirname, '../preload/index.js'),
          sandbox: true,
        },
      })
      this.window.setIgnoreMouseEvents(true, { forward: true })
      this.window.setContentProtection(true)
      this.window.on('closed', () => {
        this.window = null
      })
      if (process.env.ELECTRON_RENDERER_URL)
        void this.window.loadURL(
          `${process.env.ELECTRON_RENDERER_URL}?surface=overlay`,
        )
      else
        void this.window.loadFile(join(__dirname, '../renderer/index.html'), {
          query: { surface: 'overlay' },
        })
      this.window.webContents.on('did-finish-load', () => {
        if (this.state) this.update(this.state)
      })
    }
    this.window.setBounds(content.overlay_bounds)
    this.window.webContents.send('state', state)
    this.window.showInactive()
  }

  toggle(): void {
    this.enabled = !this.enabled
    if (this.state) this.update(this.state)
  }
  close(): void {
    this.window?.close()
    this.window = null
  }
}
