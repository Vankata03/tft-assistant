# Capture runtime boundary

Ticket 53 supplies capture, session storage, safe data refresh and Baseline publication. The integrated ticket-55 software also connects optional Live/Engine dispatch, supervised review jobs and durable idle-mode reconciliation. Tickets 42, 44, 45 and 55 remain open until their full acceptance conditions are met. Software acceptance is tied to the final tested commit in the owner's handoff; this document does not establish that a candidate was accepted or pushed. This boundary does not qualify Windows capture, current production data or the cause of the historical native process abort.

## Local configuration

The shell still launches `uv run tft-core` from `core/` with a fresh `TFT_CORE_TOKEN` and an open stdin pipe. The core prints the existing ready message and serves authenticated localhost WebSockets even when capture configuration is unavailable. Closing stdin requests graceful shutdown. A missing token remains a startup error.

`SessionStore.default()` uses `%LOCALAPPDATA%/tft-assistant` on Windows when `LOCALAPPDATA` is present, otherwise `~/.local/share/tft-assistant`. Configuration defaults to `~/.config/tft-assistant`. Optional local environment variables `TFT_ASSISTANT_DATA_ROOT` and `TFT_ASSISTANT_CONFIG_ROOT` select these directories. Immutable snapshots live under the data root's `snapshots` directory. Keep personal logs and host-specific paths outside tracked configuration.

Capture settings default to the configuration root's `settings.toml`; `TFT_ASSISTANT_SETTINGS` can select another file. The following template documents required fields. Its placeholder paths and patch label are not prepared assets or a qualified production configuration.

```toml
schema_version = 1
owner_name = "YOUR_VISIBLE_PLAYER_NAME"
window_title = "YOUR_CHECKED_TFT_WINDOW_TITLE"
locale = "YOUR_CLIENT_LOCALE"
expected_patch = "YOUR_REVIEWED_PATCH"
profile = "profiles/reviewed-profile.json"
game_config = "game/game.cfg"
models = "models"
model_pointer = "models/accepted.json"
names = "names/pinned-locale.json"
digits = "digits/calibrated"
patch_dir = "data/reviewed-patch"
# Optional:
# sources = "data/sources.toml"
# overrides = "overrides.toml"
# foot_offsets = "models/foot-offsets.json"
```

Paths resolve relative to this settings file. Unknown keys, missing required fields, unsupported schema versions and empty values fail visibly. `owner_name` must match the visible owner identity used for capture attribution. `window_title` selects the operator-checked game window by exact title; it does not infer identity from an executable or establish that a window is TFT. LCU must independently establish a positively identified TFT session. `locale` selects the name list and Windows OCR language pack. `expected_patch` compares against the immutable pin and records `previous_patch`; it does not establish the region's live patch.

Prepare data through the reviewed bootstrap/refresh workflow in [source provenance](source-provenance.md), explicitly pointing `tft-data refresh --snapshots` at the runtime snapshot directory. Startup also attempts refresh from `patch_dir`. A rejected source keeps qualified last-good data and its rejection warning. An empty installation without reviewed rule files and a validated snapshot remains unavailable; startup does not install example data.

The names JSON must contain `snapshot_id`, `locale` and `names`, where `names.units` maps every pinned playable unit ID to its client-locale display name. Other name groups may supply item, augment, Wisp and trait IDs from the same snapshot. Export these from checked locale source data; do not translate or invent aliases. The runtime rejects a mismatched pin or locale, missing playable units, unknown IDs and empty names.

`profile` uses the existing version-1 [capture profile](capture-boundary.md) and its checked artwork. `game_config` must establish windowed or borderless capture. For the old client it is League `game.cfg`, which supplies `[HUD] GlobalScale`. The standalone client (`TFTClient-Win64-Shipping.exe`) writes `%LOCALAPPDATA%\TFT\Saved\Config\WindowsClient\GameUserSettings.ini`, which has `FullscreenMode` (Unreal: 0 fullscreen, 1 borderless, 2 windowed) but no HUD scale. Pointing `game_config` at that file directly fails. Point it instead at a measured HUD record, and the layout reports `scale_source = "measured"`:

```toml
format = "tft-assistant-measured-hud/1"
client_settings = "C:/Users/YOU/AppData/Local/TFT/Saved/Config/WindowsClient/GameUserSettings.ini"

[hud_scale]
value = 1.0
measured_at = "YYYY-MM-DD"
client_size = [2560, 1440]
method = "How the scale was measured against the probe reference frames"
```

`client_settings` resolves relative to the record. All fields are required and unknown keys are rejected. The layout identity hashes both files, so a changed window mode or record is detected on the per-frame revalidation. The scale must come from frame measurement, never from a guess. On 2026-10-20 the bottom HUD text boxes in standalone-client frames matched the 2026-10-04 probe reference frames to the pixel at 2560×1440, which gives 1.0. Remeasure after a resolution or in-game scale change. `model_pointer` is a reviewed BoardReader pointer, and `models` contains its verified local assets. `digits` must contain genuine calibrated glyphs `0.png` through `9.png`, `minus.png` and `slash.png`. Each glyph is matched only against templates within 1.5 times its pixel width and height, so a glyph set belongs to the client size it was cut at; cut a new set after a resolution change. Native capture wires DigitTemplates, local RapidOCR models and Windows.Media.Ocr through HybridOCR. Missing glyphs, models or the locale language pack leave capture unavailable. This wiring does not replace the required probe benchmark or qualify the chosen OCR route's accuracy.

## Serialized session lifecycle

`tft_core.app.run` constructs CoreServer in managed lifecycle mode and starts CaptureRuntime and GameflowWatcher. `CaptureRuntime.update(GameflowUpdate)` serializes session transitions. The production LCU adapter requires a positive numeric game ID and an explicit, consistent literal `TFT` mode in session metadata. Queue numbers alone establish nothing. Parsing and mode behavior are verified against external fixtures; actual Windows LCU payload coverage remains a device check.

Repeated InProgress or Reconnect updates keep one worker and one game-start event. The worker uses the actual CaptureRunner, CapturePipeline, reviewed profile and SessionStore. A restart or reattachment loads the original historical data snapshot and game-start identities. Existing profile and model-pointer hashes must match. Missing historical pins cannot be replaced by current data. Worker exceptions become visible status and durable capture events. Invalid phase responses become client-unavailable updates; unexpected discovery failures are reported and retried rather than silently ending the watcher.

Client disappearance, ambiguous mode, a different active game ID or loss of phase stops capture, clears content and records an interval gap. The original game remains unfinished and can reattach. When a different positively identified TFT game arrives, the runtime joins the old capture thread and requires successful native/media finalization before calling `SessionStore.detach_game(expected_game_id, reason=...)`. Detach appends `session_detached`, releases storage ownership and selects the next-session default without adding game_end or placement. The old header, historical data/model/profile identity and logged mode remain intact; reconnecting that ID restores them. A timed-out writer or failed finalization keeps switching blocked. Callback generations prevent queued observations or failures from the detached worker from affecting the new game. New games pin current validated data; switching does not publish a pending refresh during InProgress. Only EndOfGame or WaitingForStats with the matching positively identified TFT game permits finalization. The worker closes the native source, calibration round, pipeline and media before `SessionStore.end_game()`. Terminal phase confirms lifecycle completion, not placement: unavailable placement stays null.

`completed_game` copies the finished SessionStore record and adds `final_mode`, taken before the next-session reset. Its stored `mode` and `review_locked` remain authoritative. A pre-run Silent game and an unlocked Silent game after start-run have different review permissions; dispatch must not derive the lock from the mode name.

## Capture publication and fight history

Capture results cross into the event loop through one replaceable frame and one scheduled drain. `CaptureRuntime.next_snapshot()` is a queue of capacity one: a slow consumer receives the latest pending snapshot. The snapshot retains original capture fields and adds `capture_status`, including transport/window availability. `EngineRuntime` consumes current observations through the bounded latest-value worker and checks the active game, installed Live permission, current mode, pinned data and capturing status before dispatch. Capture itself does not import Live or call the full Engine evaluation pipeline.

CoreServer publishes Baseline state using only its allowlisted features. Unavailable capture suppresses dependent content. Silent publishes status/staleness and logs capture; it publishes no game content or voice. Capture carries physical client bounds, configuration identity and reviewed anchors through the surface-geometry boundary. The Windows shell converts these through native per-monitor physical-pixel/DIP APIs and refuses stale, mismatched, spanning or unsupported geometry. Missing configuration keeps the overlay unavailable. Actual Windows geometry, click-through and display exclusion remain ticket-49 checks. Completed or paused games and failed workers clear the handoff. Shutdown closes the queue so waiting consumers receive `asyncio.QueueShutDown`.

`project_fight_history(events, captured_at, round_types=...)` projects the causal log prefix into fresh `log_projection` fields. The actual worker persists the projected fields in each snapshot before handing it off; replay therefore sees the same certificate. The projection retains only the relevant historical events in memory and does not reread the growing game log for every frame.

`recent_opponent_fights` contains ordered confirmed start/result pairs with `opponent_id`, `round_id`, the original fight-start `read_at`, `result_read_at` and `result`. Pinned PvE/carousel rounds are excluded. Unknown round kinds cannot certify coverage. Historical encounter timestamps do not become fresh facts when a new snapshot is produced.

`recent_opponent_fights_complete` is a literal boolean. It becomes true only after capture observes the pinned schedule's first round and a fresh recognized phase, with an uninterrupted prefix and no pending fight. Late attachment, restart gaps, unavailable phase/opponent/HP coverage, malformed or incomplete fights and window gaps invalidate it. A later good frame does not repair a missing prefix. A future event cannot certify an earlier snapshot. No rolling-window recovery or matchmaking reset rule is assumed. Ticket 41 consumes this certificate with a separately sourced recent-opponent exclusion policy; without that policy or certificate, threat adjustments remain unavailable.

## Corrective review and display boundaries

Qualified observed Lines use counted paid refreshes and the original valuation state, immutable data, history and random tape. Later financial observations qualify action completeness; they do not seed valuation with future board deployment, HP, fights or placement. Qualification checks the complete observed financial horizon, even with zero confirmed rolls. Unsupported or incomplete finances remain unavailable. Counted refreshes are additional to natural shops and may be truncated by affordability or death. No intent or chosen gold floor is inferred, and separate reward timing can leave an ordinary PvP capture unavailable.

Pivot review joins displayed calls against the actual first divergent movement, including event sequence when clocks are equal. Returning to the original target resets that provenance. Adoption confirmation remains separate from onset, and a later call cannot suppress `taken_without_call`. This observed transition supplies no synthetic pivot advice, show acknowledgement, cost or follow-rate denominator. Production `reader_disagreement` events retain protected Debug access and matching keyframes when those artifacts exist; absent media remains unavailable.

Review-notice publication and visible display are separate events. Qualification requires a typed `review_notice_shown` receipt through renderer visibility checks, preload, owned-window IPC, CoreLink and authenticated core validation. Game, report, evidence, job and notice-delivery identities must match the current finished-game notice. Finished-game mode and review lock remain authoritative even after idle-mode changes. Active games, hidden or transparent notices, stale identities and superseded notices cannot qualify display. Native compositor and Windows paint timing still require device evidence.

Acknowledged display latency is measured from confirmed game end, with lateness after 30 seconds. Durable notice receipts belong in the atomic `reviews/<game_id>.notice.json` sidecar, outside game logs, report graphs, tags and job inputs. They must not alter report or job identity, trigger regeneration or enter actionable-advice and follow-rate accounting. A malformed sidecar must produce a bounded error without killing the authenticated client's review consumer. Independent review accepted ancestor visibility and malformed-sidecar recovery at `eb5c88d0cdc97619ef9396b18ad1a6c6c2228fe1`. That bounded software acceptance does not qualify native compositor behavior or Windows paint timing.

## Refresh and shutdown deadlines

Refresh runs only at startup, Lobby or confirmed game end. Observed active LCU phases block publication before settings, data, model or session initialization is attempted; an absent capture log does not establish safety. Identity/client loss retains the guard. A safe Lobby after successful worker finalization, or a matching confirmed end even when no log started, releases it without synthesizing a game outcome. Repeated safe triggers coalesce into one task. It stages immutable candidates on a dedicated daemon thread and publishes on the event loop only outside an active game. A game retains its original object and identity even when a candidate finishes later. Qualified last-good data and source warnings remain available. Cancelling a network task does not cancel its HTTP operation; shutdown reports interruption and prevents later publication. The daemon avoids the default executor's process-exit wait, and the source's configured HTTP timeout still bounds its request.

The core gives capture eight seconds to stop. Runtime SegmentRecorder allows five seconds for flushing plus up to one second to stop its encoder and join its worker; Electron allows ten seconds before its existing child termination fallback. Native source close and pipeline close execute once on the owning capture thread. A stalled native worker produces `capture_shutdown_timeout`, retains an unfinished log and reports possible incomplete media. A close failure produces `capture_finalization_failed`; a confirmed terminal phase does not convert that failure into a finished game.

Video queue overflow and encoder failures produce gap/status events. A recorder deadline reports incomplete media, aborts queued encoding and terminates only its own encoder subprocess. If that subprocess ignores termination, the recorder kills it after a bounded grace period. Python is not forcibly exited. If Electron's ten-second deadline expires, it emits an explicit incomplete-media/recoverable-log warning before terminating its child. Source-driver hangs and forced shell termination may still interrupt final persistence; these are reported limitations, not successful flushes.

The public tests use temporary real SessionStore/DataStore instances, external LCU/window/OCR fixtures, authenticated WebSockets, a slow local HTTP response, EOF in a real core process and a real stalled encoder subprocess. Existing classifier, RapidOCR and FFmpeg tests exercise local CPU/model/codec behavior. These results do not establish Windows driver behavior, production profile/name/glyph coverage, target latency or a causal fix for ticket 50's historical native abort. Tickets 48, 49 and 50 retain those qualifications.
