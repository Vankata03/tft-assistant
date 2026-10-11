// Generated from schemas/messages.schema.json by `npm run gen:types`. Do not edit.
// The source of truth is core/src/tft_core/messages.py (`uv run tft-schemas`).

/**
 * Any message the core sends to the shell.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "CoreMessage".
 */
export type CoreMessage = Gameflow | SessionModeState | ErrorMessage | BaselineState
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
export type UiMessage = Hello | SetSessionMode | RequestBaselineState | SelectGuide | SurfaceShown

/**
 * Core and shell WebSocket messages, schema version 1.
 */
export interface Messages {
  [k: string]: unknown
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "AugmentTier".
 */
export interface AugmentTier {
  entity: EntityDisplay
  global_tier: string | null
  in_guide: boolean
  offer_index: number | null
  offered: boolean
  tier: string | null
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "EntityDisplay".
 */
export interface EntityDisplay {
  cost: number
  icon: string
  id: string
  name: string
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "BaselineContent".
 */
export interface BaselineContent {
  anchors: SurfaceAnchor[]
  augments: AugmentTier[]
  faced: FacedResult[]
  guides: GuideSummary[]
  overlay_allowed: boolean
  overlay_bounds: OverlayBounds | null
  par: ParChance
  patch: string
  phase: 'planning' | 'roll_down' | 'augment' | 'carousel' | 'combat' | 'end' | 'unknown'
  recipes: ItemRecipe[]
  round_id: string | null
  selected: GuideDisplay | null
  shop: ShopHighlight[]
  snapshot_id: string
  warnings: string[]
  wisps: WispWorth[]
  xp_hint: XpHint | null
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "SurfaceAnchor".
 */
export interface SurfaceAnchor {
  height: number
  index: number
  kind: 'shop' | 'level' | 'par' | 'augment' | 'carousel' | 'wisp'
  width: number
  x: number
  y: number
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "FacedResult".
 */
export interface FacedResult {
  name: string
  result: 'win' | 'loss' | 'draw'
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "GuideSummary".
 */
export interface GuideSummary {
  id: string
  name: string
  tier: string
  units: EntityDisplay[]
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "OverlayBounds".
 */
export interface OverlayBounds {
  height: number
  width: number
  x: number
  y: number
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "ParChance".
 */
export interface ParChance {
  paused: string | null
  probability: number | null
  uncertain: boolean
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "ItemRecipe".
 */
export interface ItemRecipe {
  components: RecipeComponent[]
  item: EntityDisplay
  unit: EntityDisplay
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "RecipeComponent".
 */
export interface RecipeComponent {
  entity: EntityDisplay
  held: boolean
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "GuideDisplay".
 */
export interface GuideDisplay {
  alternatives: string[]
  carousel: EntityDisplay[]
  early_layout: LayoutUnit[]
  final_layout: LayoutUnit[]
  id: string
  name: string
  stage_plan: {
    [k: string]: string | number
  }[]
  stage_tips: {
    [k: string]: string
  }
  tier: string
  units: EntityDisplay[]
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "LayoutUnit".
 */
export interface LayoutUnit {
  entity: EntityDisplay
  position: number | null
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "ShopHighlight".
 */
export interface ShopHighlight {
  entity: EntityDisplay
  in_guide: boolean
  slot: number
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "WispWorth".
 */
export interface WispWorth {
  entity: EntityDisplay
  offered_slot: number | null
  paired_standard_error: number | null
  source: string
  worth: number | null
  worth_label: ('worth_it' | 'situational' | 'skip' | 'unavailable') | null
  worth_stage: string | null
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "XpHint".
 */
export interface XpHint {
  buys: number
  gold: number
  passive_xp: number
  target_level: number
  target_round: string
  text: string
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "BaselineState".
 */
export interface BaselineState {
  content: BaselineContent | null
  mode: 'silent' | 'baseline' | 'live'
  stale: PausedField[]
  status: string
  type: 'baseline_state'
  v: 1
  voice: StageVoice | null
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "PausedField".
 */
export interface PausedField {
  age_seconds: number | null
  field: string
  reason: string
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "StageVoice".
 */
export interface StageVoice {
  id: string
  text: string
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
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "RequestBaselineState".
 */
export interface RequestBaselineState {
  type: 'request_baseline_state'
  v: 1
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "SelectGuide".
 */
export interface SelectGuide {
  guide_id: string
  type: 'select_guide'
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
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "SurfaceShown".
 */
export interface SurfaceShown {
  content_id: string
  surface: 'cockpit' | 'overlay' | 'voice'
  timestamp: string
  type: 'surface_shown'
  v: 1
}
