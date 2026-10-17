// The shell's end of the localhost WebSocket. The main process is the only
// client; it relays state to the windows over IPC.
import { randomUUID } from 'node:crypto'
import type {EvidencePage,LiveSurfaceShown,LivePreviewShown,PinLine,RequestEvidencePage,RequestReview,ReviewResponse,ReviewGames} from '../shared/messages'
import { EventEmitter } from 'node:events'
import {
  type CoreMessage,
  parseCoreMessage,
  SCHEMA_VERSION,
  type SessionMode,
  type UiMessage,
} from '../shared/protocol'

export class CoreLink extends EventEmitter<{
  message: [CoreMessage]
  closed: []
}> {
  private socket: WebSocket | null = null
  private pending = new Map<string,{resolve:(page:EvidencePage|ReviewResponse|ReviewGames)=>void;reject:(error:Error)=>void;timer:ReturnType<typeof setTimeout>}>()

  connect(port: number, token: string): void {
    this.close()
    const socket = new WebSocket(`ws://127.0.0.1:${port}/`)
    this.socket = socket
    socket.addEventListener('open', () =>
      this.send({ v: SCHEMA_VERSION, type: 'hello', token }),
    )
    socket.addEventListener('message', (event) => {
      if (this.socket !== socket) return
      const message =
        typeof event.data === 'string' ? parseCoreMessage(event.data) : null
      if (message) {
        if ((message.type==='evidence_page'||message.type==='review_response'||message.type==='review_games'||message.type==='error')&&message.request_id) {
          const pending=this.pending.get(message.request_id)
          if(pending){clearTimeout(pending.timer);this.pending.delete(message.request_id);if(message.type==='error')pending.reject(new Error(message.message));else pending.resolve(message)}
        }
        this.emit('message', message)
      }
      else console.warn('core link: ignored a message it could not parse')
    })
    socket.addEventListener('close', () => {
      if (this.socket !== socket) return
      this.socket = null
      this.rejectPending()
      this.emit('closed')
    })
  }

  setMode(mode: SessionMode): void {
    this.send({ v: SCHEMA_VERSION, type: 'set_session_mode', mode })
  }

  requestBaseline(): void {
    this.send({ v: SCHEMA_VERSION, type: 'request_baseline_state' })
  }

  requestLive(): void {this.send({v:SCHEMA_VERSION,type:'request_live_state'})}
  requestGeometry(): void {this.send({v:SCHEMA_VERSION,type:'request_surface_geometry'})}
  livePreviewShown(message:Omit<LivePreviewShown,'type'|'v'>): void {this.send({v:SCHEMA_VERSION,type:'live_preview_shown',...message})}
  liveShown(message:Omit<LiveSurfaceShown,'type'|'v'>): void {this.send({v:SCHEMA_VERSION,type:'live_surface_shown',...message})}
  pinLine(message:Omit<PinLine,'type'|'v'>): void {this.send({v:SCHEMA_VERSION,type:'pin_line',...message})}
  evidencePage(message:Omit<RequestEvidencePage,'v'|'type'|'request_id'>):Promise<EvidencePage> {
    if(this.socket?.readyState!==WebSocket.OPEN)return Promise.reject(new Error('Core not connected'))
    const request_id=randomUUID()
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.pending.delete(request_id);reject(new Error('Evidence request timed out'))},5000)
      this.pending.set(request_id,{resolve:page=>resolve(page as EvidencePage),reject,timer})
      this.send({v:SCHEMA_VERSION,type:'request_evidence_page',request_id,...message})
    })
  }
  requestReview(message:Omit<RequestReview,'v'|'type'|'request_id'>):Promise<ReviewResponse>{
    if(this.socket?.readyState!==WebSocket.OPEN)return Promise.reject(new Error('Core not connected'))
    const request_id=randomUUID()
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.pending.delete(request_id);reject(new Error('Review request timed out'))},10000)
      this.pending.set(request_id,{resolve:page=>resolve(page as ReviewResponse),reject,timer})
      this.send({v:SCHEMA_VERSION,type:'request_review',request_id,...message})
    })
  }
  reviewGames():Promise<ReviewGames>{
    if(this.socket?.readyState!==WebSocket.OPEN)return Promise.reject(new Error('Core not connected'))
    const request_id=randomUUID()
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.pending.delete(request_id);reject(new Error('Review list timed out'))},10000)
      this.pending.set(request_id,{resolve:page=>resolve(page as ReviewGames),reject,timer})
      this.send({v:SCHEMA_VERSION,type:'request_review_games',request_id})
    })
  }
  private rejectPending(): void {
    for(const pending of this.pending.values()){clearTimeout(pending.timer);pending.reject(new Error('Core connection changed'))}
    this.pending.clear()
  }

  selectGuide(guideId: string): void {
    this.send({ v: SCHEMA_VERSION, type: 'select_guide', guide_id: guideId })
  }

  reportShown(
    surface: 'cockpit' | 'overlay' | 'voice',
    contentId: string,
    timestamp: string,
  ): void {
    this.send({
      v: SCHEMA_VERSION,
      type: 'surface_shown',
      surface,
      content_id: contentId,
      timestamp,
    })
  }

  close(): void {
    const socket = this.socket
    this.socket = null
    socket?.close()
    this.rejectPending()
  }

  private send(message: UiMessage): void {
    if (this.socket?.readyState === WebSocket.OPEN)
      this.socket.send(JSON.stringify(message))
  }
}
