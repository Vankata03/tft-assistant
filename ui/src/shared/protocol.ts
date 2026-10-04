// Runtime side of the generated message types in ./messages.ts.
import type { CoreMessage, SessionMode, UiMessage } from './messages'

export type { CoreMessage, SessionMode, UiMessage }

/** Fails to compile when the core's schema version changes and the types are regenerated. */
export const SCHEMA_VERSION: CoreMessage['v'] & UiMessage['v'] = 1

export const SESSION_MODES: readonly SessionMode[] = ['silent', 'baseline', 'live']

const CORE_MESSAGE_TYPES: Record<CoreMessage['type'], true> = {
  gameflow: true,
  session_mode: true,
  error: true,
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
  if (v !== SCHEMA_VERSION || typeof type !== 'string' || !(type in CORE_MESSAGE_TYPES)) return null
  return data as CoreMessage
}
