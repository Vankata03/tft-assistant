// Starts the Python core as a child process and restarts it when it dies.
//
// Each spawn gets a fresh token. The core prints one JSON line,
// {"event": "ready", "port": N, "v": 1}, once its WebSocket listens. The core
// exits when its stdin closes, so stop() ends it gracefully.
import { randomBytes } from 'node:crypto'
import { EventEmitter } from 'node:events'
import { createInterface } from 'node:readline'
import type { Readable, Writable } from 'node:stream'
import type { CoreStatus } from '../shared/state'
import { RestartPolicy } from './restartPolicy'

/** The parts of a ChildProcess the supervisor uses, so tests can fake it. */
export interface CoreChild {
  readonly stdin: Writable | null
  readonly stdout: Readable | null
  readonly stderr: Readable | null
  kill(): boolean
  on(event: 'exit', listener: (code: number | null, signal: string | null) => void): this
  on(event: 'error', listener: (error: Error) => void): this
}

export interface CoreReady {
  port: number
  token: string
}

export interface SupervisorOptions {
  spawnCore: (token: string) => CoreChild
  policy?: RestartPolicy
  readyTimeoutMs?: number
  stopTimeoutMs?: number
  now?: () => number
  log?: (line: string) => void
}

export class CoreSupervisor extends EventEmitter<{
  status: [CoreStatus]
  ready: [CoreReady]
  stderr: [string]
}> {
  private child: CoreChild | null = null
  private stopping = false
  private restartTimer: NodeJS.Timeout | null = null
  private readonly policy: RestartPolicy
  private readonly readyTimeoutMs: number
  private readonly stopTimeoutMs: number
  private readonly now: () => number
  private readonly log: (line: string) => void
  status: CoreStatus = 'starting'

  constructor(private readonly options: SupervisorOptions) {
    super()
    this.policy = options.policy ?? new RestartPolicy()
    this.readyTimeoutMs = options.readyTimeoutMs ?? 30_000
    this.stopTimeoutMs = options.stopTimeoutMs ?? 3_000
    this.now = options.now ?? Date.now
    this.log = options.log ?? console.log
  }

  start(): void {
    this.stopping = false
    this.spawn()
  }

  /** Restart by hand after the supervisor gave up. */
  restartNow(): void {
    this.policy.reset()
    if (this.restartTimer) clearTimeout(this.restartTimer)
    this.restartTimer = null
    if (this.child) this.child.kill()
    else this.spawn()
  }

  /** The core misbehaved while alive (for example its WebSocket dropped); kill it so it restarts. */
  recycle(reason: string): void {
    if (!this.child || this.stopping) return
    this.log(`core: recycling (${reason})`)
    this.child.kill()
  }

  /** Stop for good: close stdin, then kill if the core has not exited in time. */
  async stop(): Promise<void> {
    this.stopping = true
    if (this.restartTimer) clearTimeout(this.restartTimer)
    this.restartTimer = null
    const child = this.child
    if (!child) return
    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => {
        child.kill()
        resolve()
      }, this.stopTimeoutMs)
      child.on('exit', () => {
        clearTimeout(timer)
        resolve()
      })
      child.stdin?.end()
    })
  }

  private setStatus(status: CoreStatus): void {
    this.status = status
    this.emit('status', status)
  }

  private spawn(): void {
    this.restartTimer = null
    const token = randomBytes(32).toString('hex')
    this.setStatus('starting')
    let child: CoreChild
    try {
      child = this.options.spawnCore(token)
    } catch (error) {
      this.log(`core: spawn failed: ${String(error)}`)
      this.onDeath()
      return
    }
    this.child = child
    let ended = false
    const readyTimer = setTimeout(() => {
      this.log('core: no ready line in time; killing it')
      child.kill()
    }, this.readyTimeoutMs)

    if (child.stdout) {
      createInterface({ input: child.stdout }).on('line', (line) => {
        const port = parseReadyLine(line)
        if (port === null || ended) return
        clearTimeout(readyTimer)
        this.setStatus('running')
        this.emit('ready', { port, token })
      })
    }
    child.stderr?.setEncoding('utf8')
    child.stderr?.on('data', (chunk: string) => this.emit('stderr', chunk))

    const end = (why: string): void => {
      if (ended) return
      ended = true
      clearTimeout(readyTimer)
      if (this.child === child) this.child = null
      this.log(`core: ${why}`)
      if (!this.stopping) this.onDeath()
    }
    child.on('exit', (code, signal) => end(`exited (code ${code}, signal ${signal})`))
    child.on('error', (error) => end(`process error: ${error.message}`))
  }

  private onDeath(): void {
    const decision = this.policy.onCrash(this.now())
    if (decision.kind === 'give-up') {
      this.log('core: too many restarts in 5 minutes; giving up')
      this.setStatus('stopped')
      return
    }
    this.log(`core: restarting in ${decision.delayMs} ms`)
    this.setStatus('restarting')
    this.restartTimer = setTimeout(() => this.spawn(), decision.delayMs)
  }
}

/** The port from the core's ready line, or null for any other line. */
export function parseReadyLine(line: string): number | null {
  try {
    const data: unknown = JSON.parse(line)
    if (typeof data !== 'object' || data === null) return null
    const { event, port } = data as { event?: unknown; port?: unknown }
    return event === 'ready' && Number.isInteger(port) ? (port as number) : null
  } catch {
    return null
  }
}
