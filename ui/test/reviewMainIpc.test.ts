import {execFileSync} from 'node:child_process'
import {mkdtempSync, readFileSync, readdirSync, rmSync} from 'node:fs'
import {tmpdir} from 'node:os'
import {delimiter, join, resolve} from 'node:path'
import {expect, it, vi} from 'vitest'
import type {CoachApi} from '../src/preload'

const native = vi.hoisted(() => ({
  ui: '', root: '', stopped: false, quit: () => {}, coach: null as CoachApi | null,
  handlers: new Map<string, (event: unknown, input?: unknown) => unknown>(),
}))

// Only Electron's external platform is replaced. Main/preload, supervision,
// authenticated WebSocket, the Python app and the review child all run normally.
vi.mock('electron', async () => {
  const {EventEmitter} = await import('node:events')
  const app = new EventEmitter()
  native.quit = () => {
    let prevented = false
    app.emit('before-quit', {preventDefault: () => {prevented = true}})
    if (!prevented) native.stopped = true
  }
  Object.assign(app, {
    getAppPath: () => native.ui, getPath: () => native.root,
    requestSingleInstanceLock: () => true, setAppUserModelId: () => {},
    whenReady: () => Promise.resolve(), quit: native.quit,
  })
  return {
    app,
    BrowserWindow: class extends EventEmitter {
      webContents = {on: () => {}, send: () => {}}
      loadFile() {return Promise.resolve()}
      close() {this.emit('closed')}
    },
    Tray: class {on() {} setImage() {} setToolTip() {} setContextMenu() {}},
    Menu: {buildFromTemplate: (value: unknown) => value},
    nativeImage: {createFromBitmap: () => ({addRepresentation: () => {}})},
    screen: {getAllDisplays: () => []},
    globalShortcut: {register: () => {}, unregisterAll: () => {}},
    ipcMain: {on: () => {}, handle: (channel: string, handler: (event: unknown, input?: unknown) => unknown) => native.handlers.set(channel, handler)},
    ipcRenderer: {invoke: (channel: string, input?: unknown) => native.handlers.get(channel)!({}, input)},
    contextBridge: {exposeInMainWorld: (_name: string, api: CoachApi) => {native.coach = api}},
  }
})

it('regenerates a finished review through actual preload and main IPC into the owned Python child', async () => {
  const repository = resolve(process.cwd(), '..'), core = join(repository, 'core')
  const root = mkdtempSync(join(tmpdir(), 'tft-review-main-ipc-'))
  native.ui = join(repository, 'ui'); native.root = root
  const sourcePaths = [core, join(core, 'src'), ...readdirSync(join(core, 'packages')).map(name => join(core, 'packages', name, 'src'))]
  vi.stubEnv('PYTHONPATH', sourcePaths.join(delimiter))
  vi.stubEnv('UV_NO_SYNC', '1')
  vi.stubEnv('TFT_ASSISTANT_DATA_ROOT', join(root, 'logs'))
  vi.stubEnv('TFT_ASSISTANT_CONFIG_ROOT', join(root, 'config'))
  vi.stubEnv('TFT_ASSISTANT_SETTINGS', join(root, 'config', 'absent.toml'))
  vi.stubEnv('LOCALAPPDATA', root)
  vi.stubGlobal('__LIVE_ENABLED__', true)
  vi.stubGlobal('__dirname', join(native.ui, 'out', 'main'))
  try {
    const actualLog = execFileSync('uv', ['run', '--no-sync', '--project', core, 'python', '-c', `
from pathlib import Path
import shutil
from tests.test_replay_contracts import logged_game, ROOT
from tft_data import DataStore
from tft_review import ReviewService
sessions, store, _, _ = logged_game(Path(${JSON.stringify(root)}), mode='baseline')
shutil.copytree(store.root, sessions.root / 'snapshots')
ReviewService(sessions, DataStore(sessions.root / 'snapshots'), repository=ROOT).produce('901')
print(sessions.log_path('901'))
`], {cwd: core, env: process.env, timeout: 30000, encoding: 'utf8'}).trim()
    const before = readFileSync(actualLog)
    await import('../src/main/index')
    await import('../src/preload/index')
    await vi.waitFor(async () => {
      const state = await native.coach!.getState()
      expect(state.core).toBe('running')
      expect(state.gameflow?.clientRunning).toBe(false)
    }, {timeout: 10000})
    const request = {game_id: '901', operation: 'summary' as const, report_id: null,
      evidence_id: null, path: [], cursor: 0, limit: 32, moment_id: null,
      option_id: null, tag: null, name: null}
    const initial = await native.coach!.requestReview(request)
    const response = await native.coach!.requestReview({...request, operation: 'regenerate'})
    expect(response.operation).toBe('regenerate')
    expect(response.value).toEqual({state: 'queued', game_id: '901'})
    await vi.waitFor(async () => {
      expect((await native.coach!.getState()).reviewReady?.game_id).toBe('901')
    }, {timeout: 20000})
    const summary = await native.coach!.requestReview(request)
    expect(summary.value.report_id).toBe(initial.value.report_id)
    expect(readFileSync(actualLog)).toEqual(before)
  } finally {
    if (native.handlers.has('get-state')) {
      native.quit()
      await vi.waitFor(() => expect(native.stopped).toBe(true), {timeout: 12000})
    }
    vi.unstubAllGlobals(); vi.unstubAllEnvs()
    rmSync(root, {recursive: true, force: true})
  }
}, 50000)
