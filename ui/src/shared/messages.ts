// Generated from schemas/messages.schema.json by `npm run gen:types`. Do not edit.
// The source of truth is core/src/tft_core/messages.py (`uv run tft-schemas`).

/**
 * Any message the core sends to the shell.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "CoreMessage".
 */
export type CoreMessage = Gameflow | SessionModeState | ErrorMessage
/**
 * The mode the coach runs a game in. Stage 1 wires the selector only.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "SessionMode".
 */
export type SessionMode = 'silent' | 'baseline' | 'live'
/**
 * Any message the shell sends to the core.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "UiMessage".
 */
export type UiMessage = Hello | SetSessionMode

/**
 * Core and shell WebSocket messages, schema version 1.
 */
export interface Messages {
  [k: string]: unknown
}
/**
 * The League client's state and gameflow phase.
 *
 * `phase` is the client's phase string as reported (`Lobby`, `ChampSelect`,
 * `InProgress`, `Reconnect`, `PreEndOfGame` and so on); null when the client
 * is not running or reports no phase.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "Gameflow".
 */
export interface Gameflow {
  client_running: boolean
  phase: string | null
  type: 'gameflow'
  v: 1
}
/**
 * The session mode the core holds; sent on connect and on every change.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "SessionModeState".
 */
export interface SessionModeState {
  available_modes: SessionMode[]
  mode: SessionMode
  type: 'session_mode'
  v: 1
}
/**
 * The core rejected a message from the shell.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "ErrorMessage".
 */
export interface ErrorMessage {
  code: string
  message: string
  type: 'error'
  v: 1
}
/**
 * First message on every connection; the core closes it on a wrong token.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "Hello".
 */
export interface Hello {
  token: string
  type: 'hello'
  v: 1
}
/**
 * The owner picked a session mode in the tray menu.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "SetSessionMode".
 */
export interface SetSessionMode {
  mode: SessionMode
  type: 'set_session_mode'
  v: 1
}
