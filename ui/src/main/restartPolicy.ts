// When the core dies, restart it with backoff, at most 3 times in 5 minutes
// (docs/spec/runtime.md, "Crash supervision").

export interface RestartPolicyOptions {
  windowMs: number
  maxRestarts: number
  baseDelayMs: number
}

export const DEFAULT_RESTART_POLICY: RestartPolicyOptions = {
  windowMs: 5 * 60_000,
  maxRestarts: 3,
  baseDelayMs: 1_000,
}

export type RestartDecision = { kind: 'restart'; delayMs: number } | { kind: 'give-up' }

export class RestartPolicy {
  private restarts: number[] = []

  constructor(private readonly options: RestartPolicyOptions = DEFAULT_RESTART_POLICY) {}

  /** The core died unexpectedly at `now` (ms). Delays double: 1 s, 2 s, 4 s. */
  onCrash(now: number): RestartDecision {
    this.restarts = this.restarts.filter((at) => now - at < this.options.windowMs)
    if (this.restarts.length >= this.options.maxRestarts) return { kind: 'give-up' }
    const delayMs = this.options.baseDelayMs * 2 ** this.restarts.length
    this.restarts.push(now)
    return { kind: 'restart', delayMs }
  }

  /** The owner restarted the core by hand; start counting afresh. */
  reset(): void {
    this.restarts = []
  }
}
