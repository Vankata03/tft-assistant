// The shell's end of the localhost WebSocket. The main process is the only
// client; it relays state to the windows over IPC.
import { EventEmitter } from 'node:events'
import {
  type CoreMessage,
  parseCoreMessage,
  SCHEMA_VERSION,
  type SessionMode,
  type UiMessage,
} from '../shared/protocol'

export class CoreLink extends EventEmitter<{ message: [CoreMessage]; closed: [] }> {
  private socket: WebSocket | null = null

  connect(port: number, token: string): void {
    this.close()
    const socket = new WebSocket(`ws://127.0.0.1:${port}/`)
    this.socket = socket
    socket.addEventListener('open', () => this.send({ v: SCHEMA_VERSION, type: 'hello', token }))
    socket.addEventListener('message', (event) => {
      const message = typeof event.data === 'string' ? parseCoreMessage(event.data) : null
      if (message) this.emit('message', message)
      else console.warn('core link: ignored a message it could not parse')
    })
    socket.addEventListener('close', () => {
      if (this.socket !== socket) return
      this.socket = null
      this.emit('closed')
    })
  }

  setMode(mode: SessionMode): void {
    this.send({ v: SCHEMA_VERSION, type: 'set_session_mode', mode })
  }

  close(): void {
    const socket = this.socket
    this.socket = null
    socket?.close()
  }

  private send(message: UiMessage): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(message))
  }
}
