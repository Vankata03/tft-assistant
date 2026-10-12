import { EventEmitter } from 'node:events'
import { PassThrough } from 'node:stream'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { type CoreChild, CoreSupervisor, parseReadyLine } from '../src/main/coreSupervisor'
import type { CoreStatus } from '../src/shared/state'

class FakeChild extends EventEmitter implements CoreChild {
  stdin = new PassThrough()
  stdout = new PassThrough()
  stderr = new PassThrough()
  killed = false

  constructor() {
    super()
    // The real core exits when stdin closes.
    this.stdin.on('finish', () => this.exit(0))
  }

  ready(port: number): void {
    this.stdout.write(`${JSON.stringify({ event: 'ready', port, v: 1 })}\n`)
  }

  exit(code: number | null): void {
    setImmediate(() => this.emit('exit', code, null))
  }

  kill(): boolean {
    this.killed = true
    this.exit(null)
    return true
  }
}

function setup() {
  const children: FakeChild[] = []
  const statuses: CoreStatus[] = []
  const supervisor = new CoreSupervisor({
    spawnCore: () => {
      const child = new FakeChild()
      children.push(child)
      return child
    },
    now: () => Date.now(),
    log: () => {},
  })
  supervisor.on('status', (status) => statuses.push(status))
  return { supervisor, children, statuses }
}

const flush = () => new Promise((resolve) => setImmediate(resolve))

describe('CoreSupervisor', () => {
  beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] }))
  afterEach(() => vi.useRealTimers())

  it('reports ready with the port and the token it gave the core', async () => {
    const { supervisor, children } = setup()
    const ready = vi.fn()
    supervisor.on('ready', ready)
    supervisor.start()
    children[0]!.ready(51234)
    await flush()
    expect(ready).toHaveBeenCalledWith({ port: 51234, token: expect.stringMatching(/^[0-9a-f]{64}$/) })
    expect(supervisor.status).toBe('running')
  })

  it('restarts a dead core with backoff and gives up after 3 restarts in 5 minutes', async () => {
    const { supervisor, children, statuses } = setup()
    supervisor.start()
    for (const delay of [1_000, 2_000, 4_000]) {
      const count = children.length
      children.at(-1)!.exit(1)
      await flush()
      expect(supervisor.status).toBe('restarting')
      await vi.advanceTimersByTimeAsync(delay - 1)
      expect(children).toHaveLength(count)
      await vi.advanceTimersByTimeAsync(1)
      expect(children).toHaveLength(count + 1)
    }
    children.at(-1)!.exit(1)
    await flush()
    expect(supervisor.status).toBe('stopped')
    await vi.advanceTimersByTimeAsync(10 * 60_000)
    expect(children).toHaveLength(4)
    expect(statuses.at(-1)).toBe('stopped')
  })

  it('restartNow brings a stopped core back', async () => {
    const { supervisor, children } = setup()
    supervisor.start()
    for (let i = 0; i < 4; i++) {
      children.at(-1)!.exit(1)
      await flush()
      await vi.advanceTimersByTimeAsync(5_000)
    }
    expect(supervisor.status).toBe('stopped')
    supervisor.restartNow()
    expect(children).toHaveLength(5)
    expect(supervisor.status).toBe('starting')
  })

  it('kills a core that never prints its ready line', async () => {
    const { supervisor, children } = setup()
    supervisor.start()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(children[0]!.killed).toBe(true)
    await flush()
    expect(supervisor.status).toBe('restarting')
  })

  it('stop closes stdin and does not restart', async () => {
    const { supervisor, children } = setup()
    supervisor.start()
    children[0]!.ready(1)
    await flush()
    await supervisor.stop()
    expect(children[0]!.killed).toBe(false)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(children).toHaveLength(1)
  })

  it('allows the core capture grace before forcing a stop', async () => {
    const child = new FakeChild()
    child.stdin.removeAllListeners('finish')
    const supervisor = new CoreSupervisor({ spawnCore: () => child, log: () => {} })
    supervisor.start()
    const stopped = supervisor.stop()
    await vi.advanceTimersByTimeAsync(8_500)
    expect(child.killed).toBe(false)
    child.exit(0)
    await stopped
  })

  it('reports incomplete capture before forcing an overdue child to stop', async () => {
    const child = new FakeChild()
    child.stdin.removeAllListeners('finish')
    const warnings: string[] = []
    const supervisor = new CoreSupervisor({ spawnCore: () => child, log: () => {} })
    supervisor.on('stderr', (line) => warnings.push(line))
    supervisor.start()
    const stopped = supervisor.stop()
    await vi.advanceTimersByTimeAsync(10_000)
    await stopped
    expect(child.killed).toBe(true)
    expect(warnings.join(' ')).toContain('media may be incomplete')
  })
})

describe('parseReadyLine', () => {
  it('reads the port', () => {
    expect(parseReadyLine('{"event": "ready", "port": 50123, "v": 1}')).toBe(50123)
  })

  it.each(['', 'starting', '{"event": "ready"}', '{"event": "other", "port": 1}', '{"event": "ready", "port": "1"}'])(
    'ignores %j',
    (line) => expect(parseReadyLine(line)).toBeNull(),
  )
})
