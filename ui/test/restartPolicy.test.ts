import { describe, expect, it } from 'vitest'
import { RestartPolicy } from '../src/main/restartPolicy'

const MINUTE = 60_000

describe('RestartPolicy', () => {
  it('backs off 1 s, 2 s, 4 s and gives up on the fourth crash within 5 minutes', () => {
    const policy = new RestartPolicy()
    expect(policy.onCrash(0)).toEqual({ kind: 'restart', delayMs: 1_000 })
    expect(policy.onCrash(10_000)).toEqual({ kind: 'restart', delayMs: 2_000 })
    expect(policy.onCrash(20_000)).toEqual({ kind: 'restart', delayMs: 4_000 })
    expect(policy.onCrash(30_000)).toEqual({ kind: 'give-up' })
  })

  it('forgets restarts older than 5 minutes', () => {
    const policy = new RestartPolicy()
    policy.onCrash(0)
    policy.onCrash(1 * MINUTE)
    policy.onCrash(2 * MINUTE)
    // The first restart has left the window, so one slot is free again.
    expect(policy.onCrash(5 * MINUTE)).toEqual({ kind: 'restart', delayMs: 4_000 })
    expect(policy.onCrash(5 * MINUTE + 1)).toEqual({ kind: 'give-up' })
  })

  it('restarts steadily when crashes are more than 5 minutes apart', () => {
    const policy = new RestartPolicy()
    for (let i = 0; i < 10; i++) {
      expect(policy.onCrash(i * 6 * MINUTE)).toEqual({ kind: 'restart', delayMs: 1_000 })
    }
  })

  it('reset starts counting afresh', () => {
    const policy = new RestartPolicy()
    for (const at of [0, 1, 2]) policy.onCrash(at)
    expect(policy.onCrash(3)).toEqual({ kind: 'give-up' })
    policy.reset()
    expect(policy.onCrash(4)).toEqual({ kind: 'restart', delayMs: 1_000 })
  })
})
