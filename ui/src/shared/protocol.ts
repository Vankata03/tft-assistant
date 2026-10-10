// Runtime side of the generated message types in ./messages.ts.
import type { CoreMessage, SessionMode, UiMessage } from './messages'

export type { CoreMessage, SessionMode, UiMessage }

/** Fails to compile when the core's schema version changes and the types are regenerated. */
export const SCHEMA_VERSION: CoreMessage['v'] & UiMessage['v'] = 1

export const SESSION_MODES: readonly SessionMode[] = [
  'silent',
  'baseline',
  'live',
]

const CORE_MESSAGE_TYPES: Record<CoreMessage['type'], true> = {
  gameflow: true,
  session_mode: true,
  error: true,
  baseline_state: true,
}

/** Parse a message from the core; null for another schema version or an unknown type. */
export function parseCoreMessage(raw: string): CoreMessage | null {
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof data !== 'object' || data === null) return null
  const { v, type } = data as { v?: unknown; type?: unknown }
  if (
    v !== SCHEMA_VERSION ||
    typeof type !== 'string' ||
    !(type in CORE_MESSAGE_TYPES)
  )
    return null
  if (type === 'baseline_state') {
    const state = data as Record<string, unknown>
    if (
      !SESSION_MODES.includes(state.mode as SessionMode) ||
      typeof state.status !== 'string' ||
      !Array.isArray(state.stale)
    )
      return null
    if (
      state.mode !== 'baseline' &&
      (state.content !== null || state.voice !== null)
    )
      return null
    if (state.content !== null) {
      if (typeof state.content !== 'object' || state.content === null)
        return null
      const content = state.content as Record<string, unknown>
      if (
        typeof content.patch !== 'string' ||
        typeof content.snapshot_id !== 'string'
      )
        return null
      if (
        ![
          'guides',
          'shop',
          'recipes',
          'augments',
          'wisps',
          'faced',
          'warnings',
        ].every((key) => Array.isArray(content[key]))
      )
        return null
    }
  }
  return data as CoreMessage
}
