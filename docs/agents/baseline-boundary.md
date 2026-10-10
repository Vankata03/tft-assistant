# Baseline surfaces boundary

Ticket 43 provides the Baseline controller, authenticated WebSocket messages, Electron windows and React surfaces. Ticket 45 owns the running application's capture/data lifecycle. Ticket 44 can add a separate Live state and renderer without routing Baseline requests through the Live advisor.

## Core publication and requests

`CoreServer.publish_baseline(data=..., snapshot=..., faced=..., status=..., round_start=..., anchors=..., overlay_bounds=..., overlay_allowed=...)` accepts the validated, game-pinned `DataSnapshot` and a capture snapshot. It copies capture values into immutable mappings. The initial authenticated handshake still returns `gameflow`, then `session_mode`. The shell sends `request_baseline_state` to subscribe; subsequent publications and mode changes return `baseline_state`.

The snapshot contains `game_id`, `round_id`, an explicit `phase`, and `fields`. Each field contains `value`, an aware ISO `read_at` timestamp and optional `confidence`. The phase is one of `planning`, `roll_down`, `augment`, `carousel`, `combat`, `end` or `unknown`; lifecycle wiring must map a checked capture phase rather than infer planning from LCU's `InProgress` phase.

Consumed fields are `level`, `xp`, `gold`, `components`, `shop`, `augments`, `wisp`, `board` and `inventory_complete`. Shop rows use `slot` and `unit_id`; augment offers are stable IDs or rows with `augment_id`; Wisp offers use `wisp_id` and `slot`. An own board has `units` containing `unit_id`, `stars` and explicitly read equipped `items`, plus optional verified `trait_counts`. Par win chance requires `inventory_complete=true`, fresh fields and sufficient board confidence. Missing inventory or unread items pause the chip. Opponent sightings are never consumed.

`select_guide` takes `guide_id` and is accepted only in Baseline mode for a Guide in the validated snapshot. Selection is logged during a game. The controller sorts the picker by supplied tier and never filters it using the player's board. `faced` accepts names and confirmed `win`, `loss` or `draw` results only; opponent boards have no display representation.

Silent and Live modes return status and stale-field metadata with `content=null` and `voice=null`. Core models reject a Baseline body under another mode, and the shell rejects it again. Disconnects and authoritative mode changes clear cached content. During an active game, the WebSocket and selector reject upward mode changes; SessionStore's installed-package and durable mode constraints still apply.

## Static data and permitted hints

Guide final hexes come from `Guide.positions`. Interim hexes come only from `Guide.early_positions`, an additive immutable mapping for explicit checked source positions or owner overrides. Academy's position-free `earlyComp` remains unplaced. The UI states that its source layout is unavailable rather than assigning hexes.

The cockpit renders the Guide's stage tips and explicit line points, layouts, item/early-item recipes, held components, carousel priorities, shop membership, augment tiers, static Wisp worth and faced results together. Verified comp augment tiers require `Guide.cluster_id`; otherwise global tiers remain visible. No cluster mapping is guessed. Static Wisp values come from source-tagged `static.wisp_worth[id]`, or an explicit `worth` in the source-tagged Wisp rule. Missing values display as unavailable and never invoke the live Wisp evaluator.

The XP hint uses the Guide's explicit future `round` and `level`, `round_order`, `xp_table` and `rules_flags.passive_xp`, `xp_buy_amount`, `xp_buy_cost`. Passive XP counts the ordered rounds after the current round through the target. The hint states a gap; it never tells the player to level. Par win chance imports only `tft_engine.allowlist.strength`, `growth_curve_lookup` and `win_probability`. Default or carried weight/fight tunables mark the number uncertain. Invalid data or stale own fields pause the affected hint.

The import contract rejects indirect paths into the full Engine through other core modules. Only the allowlist edge is excluded from the forbidden graph, so the allowlist may call its own Engine internals. Baseline never imports `live` or calls the advice pipeline.

## Overlay, voice and shown events

Calibrated anchors have `kind`, `index`, normalized `x`, `y`, `width`, `height`; the whole rectangle must remain inside the frame. Kinds are `shop`, `level`, `par`, `augment`, `carousel`, `wisp`. No player-list anchor exists. `overlay_bounds` uses Electron desktop device-independent coordinates; lifecycle wiring must convert checked physical capture bounds where display scaling requires it. `overlay_allowed` must explicitly permit the current borderless/windowed presentation. Missing bounds, anchors or permission hides the overlay, as does having no active game. Exclusive fullscreen must leave permission false.

The overlay displays only the appropriate phase's Baseline facts. Its Electron window is transparent, non-focusable, click-through and capture-protected. Ctrl+Shift+O toggles its visibility. The implementation follows the current [Electron BrowserWindow APIs](https://www.electronjs.org/docs/latest/api/browser-window); Windows capture exclusion, anchoring, focus and exclusive-fullscreen behavior still require ticket 49's device checks.

At a planning round start, `round_start=true` permits one explicit Guide stage tip per game/stage. The renderer uses the local voice interface, deduplicates cue IDs and cancels on disconnect, downgrade or unmount. Ordinary capture updates do not cancel a spoken stage step. No local English voice produces a visible unavailable status. The deferred effect avoids speaking from React's discarded development setup; [React documents the extra setup/cleanup cycle](https://react.dev/reference/react/useEffect).

The preload exposes `selectGuide`, `setMode` and `reportShown(surface, contentId, awareTimestamp)`. The renderer reports rendered cockpit/reference revisions and nonempty overlay tags; revisions identify the validated snapshot, piece and a display hash. Voice is reported only after the local output accepts the cue. Core logs these as `ui_show` during a coached game and rejects them in Silent mode. A reconnect can report the newly shown surface again. Ticket 44 should use the same shown-event boundary for its separate Live surfaces.

## Renderer verification workflow

From `ui/`, run `npm run preview:fixture` and open `http://127.0.0.1:5178/test/browser/`. This runs the actual React renderer with a deterministic test-only preload. Its banner and synthetic entity names identify the fixture. Toolbar controls exercise unread fields, missing data, disconnect/reconnect and stage cues; the real selector and Guide buttons exercise mode and selection rendering. Add `?surface=overlay` to inspect normalized tags. The fixture is outside the production entry and absent from the production bundle.

On 2026-10-10, Zen rendered Guide A/B selection, unplaced interim units, final hexes, recipes, tiers, XP facts and par chance. Silent removed all game content; unread status remained. Upward mode changes were disabled in an active game. Disconnect cleared cached content, reconnect restored it, and rejected data showed an unavailable state. A narrow responsive viewport rendered the header/picker without horizontal spill. Stage cues showed the missing local English voice status and emitted no voice event. These are macOS browser fixture results, not Windows Electron or live-game qualification.

T3 navigation succeeded, but snapshots/evaluation timed out and resize returned `No preview automation host is available for resize in environment 4b8f2101-d1a1-4523-bd2d-c373f93963f3`. The corrected open retry returned `preview_open did not complete within 30000 ms after retry; automation host remains unavailable`. The authorized Zen fallback supplied the rendered evidence. Native console inspection later returned `Sky Computer Use request timed out`; a clean browser console is not claimed.

Production source qualification remains in ticket 48. Rejected fresh Academy IDs, unconfirmed cohorts or missing checked tables must stay explicit; retain the data layer's last good snapshot where one exists. No renderer fixture becomes production data. Ticket 49 owns Windows capture/game and voice/overlay qualification.
