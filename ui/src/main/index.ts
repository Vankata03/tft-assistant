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
import {currentLiveMember,validEvidencePath} from '../shared/liveCommands'
import type {LiveSurfaceShown,LivePreviewShown,ReviewNoticeShown,PinLine,RequestEvidencePage,RequestReview} from '../shared/messages'
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
let voiceWindow:BrowserWindow|null=null
let quitting = false
const overlay = new CoachOverlay()

function setState(patch: Partial<ShellState>): void {
  state = { ...state, ...patch }
  tray?.update(state)
  overlay.update(state)
  statusWindow?.webContents.send('state', state)
  voiceWindow?.webContents.send('state',state)
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

function createVoiceWindow():void {
  voiceWindow=new BrowserWindow({show:false,width:1,height:1,skipTaskbar:true,webPreferences:{preload:join(__dirname,'../preload/index.js'),sandbox:true,backgroundThrottling:false}})
  if(process.env.ELECTRON_RENDERER_URL)void voiceWindow.loadURL(`${process.env.ELECTRON_RENDERER_URL}?surface=voice`)
  else void voiceWindow.loadFile(join(__dirname,'../renderer/index.html'),{query:{surface:'voice'}})
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
      spawn('uv', ['run','--frozen', ...(__LIVE_ENABLED__?[]:['--no-group','live']), '--project', join(REPO_ROOT, 'core'), 'tft-core'], {
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
            live:null,
            surfaceGeometry:null,
            reviewReady:null,reviewRequest:null,
          },
    )
  })
  supervisor.on('ready', ({ port, token }) => link.connect(port, token))

  link.on('message', (message) => {
    switch (message.type) {
      case 'gameflow':
        setState({
          ...(['InProgress','Reconnect','PreEndOfGame'].includes(message.phase??'')?{reviewReady:null,reviewRequest:null}:{}),
          gameflow: {
            clientRunning: message.client_running,
            phase: message.phase,
          },
        })
        log(`gameflow: ${describeGameflow(state)}`)
        break
      case 'session_mode':
        setState({
          mode: !__LIVE_ENABLED__&&message.mode==='live'?null:message.mode,
          availableModes: message.available_modes.filter(mode=>__LIVE_ENABLED__||mode!=='live'),
          baseline: null,
          live:null,
          surfaceGeometry:null,
        })
        link.requestBaseline()
        if (__LIVE_ENABLED__) link.requestLive()
        link.requestGeometry()
        log(`session mode: ${message.mode}`)
        break
      case 'baseline_state':
        if (message.mode === state.mode) setState({ baseline: message })
        break
      case 'live_state':
        if(__LIVE_ENABLED__&&message.mode===state.mode)setState({live:message})
        break
      case 'surface_geometry':
        if(message.mode===state.mode)setState({surfaceGeometry:message})
        break
      case 'review_ready':
        if(!['InProgress','Reconnect','PreEndOfGame'].includes(state.gameflow?.phase??''))setState({reviewReady:message})
        break
      case 'error':
        setState({ error: message.message,...(message.code==='review_notice_rejected'?{reviewReady:null}:{}) })
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
      (__LIVE_ENABLED__||mode!=='live') &&
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

  ipcMain.on('review-notice-shown',(event,input:unknown)=>{
    if(state.core!=='running'||!state.reviewReady||['InProgress','Reconnect','PreEndOfGame'].includes(state.gameflow?.phase??'')||typeof input!=='object'||input===null)return
    const row=input as Omit<ReviewNoticeShown,'v'|'type'>,ready=state.reviewReady
    if(!['baseline','live'].includes(ready.mode)||!['game_id','report_id','evidence_id','job_id','notice_id'].every(key=>row[key as keyof typeof row]===ready[key as keyof typeof ready]))return
    if((row.surface==='status'&&event.sender!==statusWindow?.webContents)||(row.surface==='overlay'&&!overlay.owns(event.sender))||!['status','overlay'].includes(row.surface))return
    if(typeof row.timestamp!=='string'||!Number.isFinite(Date.parse(row.timestamp))||Date.parse(row.timestamp)<Date.parse(ready.ready_at))return
    link.reviewNoticeShown({game_id:row.game_id,report_id:row.report_id,evidence_id:row.evidence_id,job_id:row.job_id,notice_id:row.notice_id,surface:row.surface,timestamp:row.timestamp})
  })
  ipcMain.on('live-preview-shown',(_event,input:unknown)=>{
    if(!__LIVE_ENABLED__||state.core!=='running'||state.mode!=='live'||!currentLiveMember(state.live,input))return
    const row=input as Omit<LivePreviewShown,'v'|'type'>
    if(row.surface==='overlay'&&typeof row.timestamp==='string'&&row.data_snapshot_id===state.live!.content!.data_snapshot_id&&row.round_id===state.live!.content!.round_id&&state.live!.content!.next_planning?.available&&!state.live!.next_planning_invalidated)link.livePreviewShown(row)
  })
  ipcMain.on('live-shown',(_event,input:unknown)=>{
    if(!__LIVE_ENABLED__||state.core!=='running'||state.mode!=='live'||!currentLiveMember(state.live,input))return
    const row=input as Omit<LiveSurfaceShown,'v'|'type'>
    if(['cockpit','overlay','voice'].includes(row.surface)&&typeof row.decision_id==='string'&&typeof row.option_id==='string'&&typeof row.timestamp==='string')link.liveShown(row)
  })
  ipcMain.on('pin-line',(_event,input:unknown)=>{
    if(!__LIVE_ENABLED__||state.core!=='running'||state.mode!=='live'||!currentLiveMember(state.live,input))return
    const row=input as Omit<PinLine,'v'|'type'>
    if((row.line_id===null&&row.comp_id===null&&row.seed===null)||(typeof row.line_id==='string'&&typeof row.comp_id==='string'&&typeof row.seed==='string'&&/^\d{1,20}$/.test(row.seed)))link.pinLine(row)
  })
  ipcMain.handle('evidence-page',async(_event,input:unknown)=>{
    if(!__LIVE_ENABLED__||state.core!=='running'||state.mode!=='live'||!currentLiveMember(state.live,input))throw new Error('Live revision is no longer current')
    const row=input as Omit<RequestEvidencePage,'v'|'type'|'request_id'>
    if(!validEvidencePath(row.path)||!Number.isSafeInteger(row.cursor)||row.cursor<0||!Number.isSafeInteger(row.limit)||row.limit<1||row.limit>128)throw new Error('Invalid evidence path or page')
    const response=await link.evidencePage(row)
    if(!currentLiveMember(state.live,response))throw new Error('Evidence belongs to a superseded revision')
    return response
  })
  ipcMain.handle('review-games',()=>{
    if(state.core!=='running'||(state.mode==='silent'&&['InProgress','Reconnect','PreEndOfGame'].includes(state.gameflow?.phase??'')))throw new Error('Review surfaces suppressed')
    return link.reviewGames()
  })
  ipcMain.handle('review-request',async(_event,input:unknown)=>{
    if(state.core!=='running'||(state.mode==='silent'&&['InProgress','Reconnect','PreEndOfGame'].includes(state.gameflow?.phase??'')))throw new Error('Review surfaces suppressed during this game')
    if(typeof input!=='object'||input===null)throw new Error('Invalid review request')
    const row=input as Omit<RequestReview,'v'|'type'|'request_id'>
    if(typeof row.game_id!=='string'||!/^\d{1,30}$/.test(row.game_id)||!['summary','page','what_if','tag','media','regenerate'].includes(row.operation)||!validEvidencePath(row.path)||!Number.isSafeInteger(row.cursor)||row.cursor<0||!Number.isSafeInteger(row.limit)||row.limit<1||row.limit>49152)throw new Error('Invalid bounded review request')
    const response=await link.requestReview(row)
    if(state.core!=='running'||(state.mode==='silent'&&['InProgress','Reconnect','PreEndOfGame'].includes(state.gameflow?.phase??'')))throw new Error('Review permissions changed')
    return response
  })
  ipcMain.on('open-review',(event,gameId:unknown)=>{
    if(event.sender!==statusWindow?.webContents&&!overlay.owns(event.sender))return
    if(state.core!=='running'||typeof gameId!=='string'||state.reviewReady?.game_id!==gameId||['InProgress','Reconnect','PreEndOfGame'].includes(state.gameflow?.phase??''))return
    setState({reviewRequest:{game_id:gameId,serial:(state.reviewRequest?.serial??0)+1}})
    showStatus()
  })
  ipcMain.on('overlay-interactive' ,(event,input:unknown)=>{
    if(typeof input==='boolean')overlay.setInteractive(event.sender,input)
  })

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
    createVoiceWindow()
    const supervisor = startCore()
    globalShortcut.register('Control+Shift+O', () => overlay.toggle())
    app.on('before-quit', (event) => {
      if (quitting) return
      quitting = true
      overlay.close()
      voiceWindow?.close()
      voiceWindow=null
      globalShortcut.unregisterAll()
      event.preventDefault()
      void supervisor.stop().finally(() => app.quit())
    })
  })
}
