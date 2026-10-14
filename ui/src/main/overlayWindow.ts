import { BrowserWindow,screen,type WebContents } from 'electron'
import { join } from 'node:path'
import {projectOverlayGeometry} from './geometry'
import type { ShellState } from '../shared/state'

/** Native overlay stays hidden until current checked geometry permits its widgets. */
export class CoachOverlay {
  private window: BrowserWindow | null = null
  private enabled = true
  private state: ShellState | null = null
  private timer:ReturnType<typeof setInterval>|null=null

  update(state: ShellState): void {
    this.state = state
    if(!this.timer)this.timer=setInterval(()=>{if(this.state)this.update(this.state)},250)
    const projection=projectOverlayGeometry(state.surfaceGeometry,screen,Date.now(),process.platform)
    const content=state.mode==='live'?state.live?.content:state.mode==='baseline'?state.baseline?.content:null
    const inGame=['InProgress','Reconnect','PreEndOfGame'].includes(state.gameflow?.phase??'')
    const hasReview=Boolean(!inGame&&state.reviewReady&&projection.anchors.some(row=>row.kind==='review'))
    if(state.core!=='running'||(!inGame&&!hasReview)||!this.enabled||(!content&&!hasReview)||!projection.bounds){this.window?.hide();return}
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
    this.window.setBounds(projection.bounds)
    this.window.webContents.send('state', {...state,overlayGeometry:projection})
    this.window.showInactive()
  }

  owns(sender:WebContents):boolean{return sender===this.window?.webContents}

  setInteractive(sender:WebContents,interactive:boolean):void {
    if(sender!==this.window?.webContents||!this.window?.isVisible())return
    this.window.setIgnoreMouseEvents(!interactive,{forward:true})
  }

  toggle(): void {
    this.enabled = !this.enabled
    if (this.state) this.update(this.state)
  }
  close(): void {
    if(this.timer)clearInterval(this.timer)
    this.timer=null
    this.state=null
    this.window?.close()
    this.window = null
  }
}
