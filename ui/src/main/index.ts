// The shell: a tray app that starts and supervises the Python core and shows
// what the core reports. It idles in the tray until a game starts; no window
// opens on its own.
import { spawn } from 'node:child_process'
import { createWriteStream, mkdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { app, BrowserWindow, globalShortcut, ipcMain } from 'electron'
import { SESSION_MODES, type SessionMode } from '../shared/protocol'
import {
  canSelectMode,
  describeGameflow,
  INITIAL_STATE,
  type ShellState,
} from '../shared/state'
import { CoreLink } from './coreLink'
import { CoreSupervisor } from './coreSupervisor'
import { CoachTray } from './tray'
import { CoachOverlay } from './overlayWindow'

const REPO_ROOT = resolve(app.getAppPath(), '..')
const LOG_DIR = join(
  process.env.LOCALAPPDATA ?? app.getPath('userData'),
  'tft-assistant',
  'logs',
)

let state: ShellState = INITIAL_STATE
let tray: CoachTray | null = null
let statusWindow: BrowserWindow | null = null
let quitting = false
const overlay = new CoachOverlay()

function setState(patch: Partial<ShellState>): void {
  state = { ...state, ...patch }
  tray?.update(state)
  overlay.update(state)
  statusWindow?.webContents.send('state', state)
}

function showStatus(): void {
  if (statusWindow) {
    statusWindow.show()
    statusWindow.focus()
    return
  }
  statusWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 780,
    minHeight: 600,
    title: 'TFT Assistant',
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: true,
    },
  })
  statusWindow.on('closed', () => (statusWindow = null))
  if (process.env.ELECTRON_RENDERER_URL)
    void statusWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  else void statusWindow.loadFile(join(__dirname, '../renderer/index.html'))
}

function startCore(): CoreSupervisor {
  mkdirSync(LOG_DIR, { recursive: true })
  const coreLog = createWriteStream(join(LOG_DIR, 'core.log'), { flags: 'a' })
  const log = (line: string): void => {
    console.log(line)
    coreLog.write(`${new Date().toISOString()} shell ${line}\n`)
  }
  const supervisor = new CoreSupervisor({
    log,
    spawnCore: (token) =>
      spawn('uv', ['run', '--project', join(REPO_ROOT, 'core'), 'tft-core'], {
        cwd: REPO_ROOT,
        env: { ...process.env, TFT_CORE_TOKEN: token, PYTHONUNBUFFERED: '1' },
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
      }),
  })
  const link = new CoreLink()

  supervisor.on('stderr', (chunk) => {
    process.stderr.write(chunk)
    coreLog.write(chunk)
  })
  supervisor.on('status', (core) => {
    if (core !== 'running') link.close()
    setState(
      core === 'running'
        ? { core }
        : {
            core,
            gameflow: null,
            mode: null,
            availableModes: [],
            error: null,
            baseline: null,
          },
    )
  })
  supervisor.on('ready', ({ port, token }) => link.connect(port, token))

  link.on('message', (message) => {
    switch (message.type) {
      case 'gameflow':
        setState({
          gameflow: {
            clientRunning: message.client_running,
            phase: message.phase,
          },
        })
        log(`gameflow: ${describeGameflow(state)}`)
        break
      case 'session_mode':
        setState({
          mode: message.mode,
          availableModes: message.available_modes,
          baseline: null,
        })
        link.requestBaseline()
        log(`session mode: ${message.mode}`)
        break
      case 'baseline_state':
        if (message.mode === state.mode) setState({ baseline: message })
        break
      case 'error':
        setState({ error: message.message })
        log(`core rejected a message: ${message.code}: ${message.message}`)
        break
    }
  })
  link.on('closed', () => {
    if (!quitting) supervisor.recycle('WebSocket closed')
  })

  ipcMain.handle('get-state', () => state)
  ipcMain.on('set-mode', (_event, mode: unknown) => {
    if (
      SESSION_MODES.includes(mode as SessionMode) &&
      canSelectMode(state, mode as SessionMode)
    )
      link.setMode(mode as SessionMode)
  })

  ipcMain.on('select-guide', (_event, guideId: unknown) => {
    if (
      state.core === 'running' &&
      state.mode === 'baseline' &&
      typeof guideId === 'string' &&
      guideId.length <= 200
    )
      link.selectGuide(guideId)
  })

  ipcMain.on(
    'surface-shown',
    (_event, surface: unknown, contentId: unknown, timestamp: unknown) => {
      if (state.core !== 'running' || state.mode === 'silent') return
      if (
        (surface === 'cockpit' ||
          surface === 'overlay' ||
          surface === 'voice') &&
        typeof contentId === 'string' &&
        contentId.length <= 500 &&
        typeof timestamp === 'string'
      )
        link.reportShown(surface, contentId, timestamp)
    },
  )

  tray = new CoachTray({
    setMode: (mode) => {
      if (canSelectMode(state, mode)) link.setMode(mode)
    },
    showStatus,
    restartCore: () => supervisor.restartNow(),
    quit: () => app.quit(),
  })
  tray.update(state)
  supervisor.start()
  return supervisor
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.setAppUserModelId('tft-assistant')
  app.on('second-instance', showStatus)
  // A tray app keeps running with no window open.
  app.on('window-all-closed', () => {})

  void app.whenReady().then(() => {
    const supervisor = startCore()
    globalShortcut.register('Control+Shift+O', () => overlay.toggle())
    app.on('before-quit', (event) => {
      if (quitting) return
      quitting = true
      overlay.close()
      globalShortcut.unregisterAll()
      event.preventDefault()
      void supervisor.stop().finally(() => app.quit())
    })
  })
}
