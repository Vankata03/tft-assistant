// Generated from schemas/messages.schema.json by `npm run gen:types`. Do not edit.
// The source of truth is core/src/tft_core/messages.py (`uv run tft-schemas`).

/**
 * Any message the core sends to the shell.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "CoreMessage".
 */
export type CoreMessage =
  | Gameflow
  | SessionModeState
  | ErrorMessage
  | BaselineState
  | LiveState
  | EvidencePage
  | SurfaceGeometryState
  | ReviewResponse
  | ReviewGames
  | ReviewReady
/**
 * The mode the coach runs a game in. Stage 1 wires the selector only.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "SessionMode".
 */
export type SessionMode = 'silent' | 'baseline' | 'live'
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "JsonValue".
 */
export type JsonValue = unknown
/**
 * Any message the shell sends to the core.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "UiMessage".
 */
export type UiMessage =
  | Hello
  | SetSessionMode
  | RequestBaselineState
  | SelectGuide
  | SurfaceShown
  | RequestLiveState
  | RequestEvidencePage
  | LiveSurfaceShown
  | LivePreviewShown
  | PinLine
  | RequestSurfaceGeometry
  | RequestReview
  | RequestReviewGames

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
  average_placement: number | null
  changed: boolean
  entity: EntityDisplay
  global_tier: string | null
  in_guide: boolean
  offer_index: number | null
  offered: boolean
  pick_stage: number | null
  sample_count: number | null
  stale: boolean
  statistic_scope: ('global' | 'comp') | null
  statistic_source: string | null
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
  reference_source: string | null
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
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "ErrorMessage".
 */
export interface ErrorMessage {
  code: string
  message: string
  request_id: string | null
  type: 'error'
  v: 1
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "LiveState".
 */
export interface LiveState {
  content: LiveContent | null
  invalidated: {
    [k: string]: string
  }
  mode: SessionMode
  next_planning_invalidated: string | null
  observed_phase:
    ('planning' | 'roll_down' | 'augment' | 'carousel' | 'combat' | 'end' | 'unknown') | null
  ownership_qualified: boolean | null
  pin: {
    [k: string]: string
  } | null
  revision: string | null
  roster_qualified: boolean | null
  status: string
  type: 'live_state'
  v: 1
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "LiveContent".
 */
export interface LiveContent {
  advice: LiveAdviceDisplay[]
  captured_at: string
  confidence_medium_min: number | null
  data_snapshot_id: string | null
  entity_names: {
    [k: string]: string
  }
  evaluated_at: string
  evidence_id: string
  fits: LiveFitDisplay[]
  game_id: string
  lines: LiveLineDisplay[]
  model_hash: string | null
  next_planning: LiveNextPlanningPreview | null
  opponents: {
    [k: string]: JsonValue
  }[]
  ownership_valid_until: string | null
  phase: 'planning' | 'roll_down' | 'augment' | 'carousel' | 'combat' | 'end' | 'unknown'
  plan: {
    [k: string]: JsonValue
  }
  projection: LiveProjectionDisplay[]
  recommended_board: {
    [k: string]: JsonValue
  } | null
  roll_tracker: {
    [k: string]: JsonValue
  } | null
  roster_valid_until: string | null
  round_id: string
  snapshot_id: string
  warnings: string[]
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "LiveAdviceDisplay".
 */
export interface LiveAdviceDisplay {
  action: string
  anchors: {
    [k: string]: JsonValue
  }
  confidence: number
  decision_id: string
  domain: string
  evidence_path: (string | number)[]
  numbers: {
    [k: string]: number | string
  }
  option_id: string
  options: LiveOptionDisplay[]
  payload: {
    [k: string]: JsonValue
  }
  placement_impact: number
  reason: string
  urgency: 'act_this_phase' | 'soon' | 'information'
  valid_until: string | null
  validity: string[]
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "LiveOptionDisplay".
 */
export interface LiveOptionDisplay {
  action: string
  evidence_path: (string | number)[]
  expected_placement: number | null
  option_id: string
  payload: {
    [k: string]: JsonValue
  }
  reason: string
  standard_error: number | null
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "LiveFitDisplay".
 */
export interface LiveFitDisplay {
  comp_id: string
  confidence: number
  evidence_path: (string | number)[]
  score: number
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "LiveLineDisplay".
 */
export interface LiveLineDisplay {
  comp_id: string
  confidence: number
  death_probability: number
  evidence_path: (string | number)[]
  expected_placement: number
  hit_probability: number
  line_id: string
  schedule: {
    [k: string]: JsonValue
  }
  seed: string
  standard_error: number
}
/**
 * Combat's preview of the next planning call: a scheduled point, never projected state.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "LiveNextPlanningPreview".
 */
export interface LiveNextPlanningPreview {
  available: boolean
  comp_id: string | null
  evidence_path: (string | number)[]
  gold_floor: number | null
  level: number | null
  line_id: string | null
  pinned: boolean
  planning_round: string | null
  planning_snapshot_id: string | null
  reason: string | null
  round_id: string | null
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "LiveProjectionDisplay".
 */
export interface LiveProjectionDisplay {
  expected_placement: number
  gold: number
  hit_probability: number
  hp: number
  level: number
  planned_gold: number | null
  round_id: string
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "EvidencePage".
 */
export interface EvidencePage {
  game_id: string
  page: {
    [k: string]: JsonValue
  }
  request_id: string
  revision: string
  type: 'evidence_page'
  v: 1
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "SurfaceGeometryState".
 */
export interface SurfaceGeometryState {
  anchors: LiveSurfaceAnchor[]
  geometry: SurfaceGeometry | null
  mode: SessionMode
  status: string
  type: 'surface_geometry'
  v: 1
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "LiveSurfaceAnchor".
 */
export interface LiveSurfaceAnchor {
  height: number
  index: number
  kind:
    | 'shop'
    | 'level'
    | 'par'
    | 'augment'
    | 'carousel'
    | 'wisp'
    | 'xp'
    | 'player'
    | 'hex'
    | 'line'
    | 'review'
  width: number
  x: number
  y: number
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "SurfaceGeometry".
 */
export interface SurfaceGeometry {
  calibration: SurfaceCalibration
  client_bounds: PhysicalClientBounds
  coordinate_space: 'physical_pixels'
  layout_read_at: string
  layout_source_sha256: string
  profile_sha256: string
  read_at: string
  source: 'Win32-client-rectangle'
  ui_scale: number
  window_id: string
  window_mode: 'windowed' | 'borderless' | 'exclusive_fullscreen' | 'unknown'
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "SurfaceCalibration".
 */
export interface SurfaceCalibration {
  /**
   * @minItems 2
   * @maxItems 2
   */
  client_size: [unknown, unknown]
  ui_scale: number
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "PhysicalClientBounds".
 */
export interface PhysicalClientBounds {
  height: number
  width: number
  x: number
  y: number
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "ReviewResponse".
 */
export interface ReviewResponse {
  game_id: string
  operation: 'summary' | 'page' | 'what_if' | 'tag' | 'media' | 'regenerate'
  request_id: string
  type: 'review_response'
  v: 1
  value: {
    [k: string]: JsonValue
  }
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "ReviewGames".
 */
export interface ReviewGames {
  aggregates: {
    [k: string]: JsonValue
  }
  games: {
    [k: string]: JsonValue
  }[]
  request_id: string
  type: 'review_games'
  v: 1
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "ReviewReady".
 */
export interface ReviewReady {
  ended_at: string
  evidence_id: string
  game_id: string
  late: boolean
  latency_seconds: number
  mode: 'baseline' | 'live'
  ready_at: string
  report_id: string
  type: 'review_ready'
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
 * Display evidence for a scheduled preview, outside actionable attribution.
 *
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "LivePreviewShown".
 */
export interface LivePreviewShown {
  data_snapshot_id: string
  game_id: string
  preview: LiveNextPlanningPreview
  revision: string
  round_id: string
  surface: 'overlay'
  timestamp: string
  type: 'live_preview_shown'
  v: 1
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "LiveSurfaceShown".
 */
export interface LiveSurfaceShown {
  decision_id: string
  game_id: string
  option_id: string
  revision: string
  surface: 'cockpit' | 'overlay' | 'voice'
  timestamp: string
  type: 'live_surface_shown'
  v: 1
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "PinLine".
 */
export interface PinLine {
  comp_id: string | null
  game_id: string
  line_id: string | null
  revision: string
  seed: string | null
  type: 'pin_line'
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
 * via the `definition` "RequestEvidencePage".
 */
export interface RequestEvidencePage {
  cursor: number
  game_id: string
  limit: number
  /**
   * @maxItems 64
   */
  path: (string | number)[]
  request_id: string
  revision: string
  type: 'request_evidence_page'
  v: 1
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "RequestLiveState".
 */
export interface RequestLiveState {
  type: 'request_live_state'
  v: 1
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "RequestReview".
 */
export interface RequestReview {
  cursor: number
  evidence_id: string | null
  game_id: string
  limit: number
  moment_id: string | null
  name: string | null
  operation: 'summary' | 'page' | 'what_if' | 'tag' | 'media' | 'regenerate'
  option_id: string | null
  /**
   * @maxItems 64
   */
  path: (string | number)[]
  report_id: string | null
  request_id: string
  tag: ('agree' | 'disagree' | 'unsure') | null
  type: 'request_review'
  v: 1
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "RequestReviewGames".
 */
export interface RequestReviewGames {
  request_id: string
  type: 'request_review_games'
  v: 1
}
/**
 * This interface was referenced by `Messages`'s JSON-Schema
 * via the `definition` "RequestSurfaceGeometry".
 */
export interface RequestSurfaceGeometry {
  type: 'request_surface_geometry'
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
