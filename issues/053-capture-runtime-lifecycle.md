---
id: 53
title: Supervised capture and safe-refresh runtime lifecycle
labels: [implementation:task]
status: open
assignee: codex-capture-runtime
parent: 34
blocked_by: [35, 36, 37, 38, 40, 43, 51]
---

# Supervised capture and safe-refresh runtime lifecycle

This extracts the capture/data/session lifecycle prerequisite from ticket 45. Its software dependencies are closed. Final Live dispatch, review jobs, run workflows and complete runtime qualification remain in 45; historical native investigation remains the parent/final-runtime gate in 50.

## Sources

- [Runtime specification](../docs/spec/runtime.md), [capture specification](../docs/spec/capture.md) and [data refresh specification](../docs/spec/data.md).
- [Ticket 45](045-runtime-run.md), especially terminal session ordering and graceful-stop deadlines.
- [Capture boundary](../docs/agents/capture-boundary.md), [Baseline boundary](../docs/agents/baseline-boundary.md), [source provenance](../docs/agents/source-provenance.md) and [approved seams](../docs/agents/implementation.md).
- Read-only lifecycle preparation: `/tmp/tft-assistant-45-preflight.md`.

## Acceptance

- Wire the actual core process to one serialized LCU-driven capture/session lifecycle. Start one capture worker for a positively identified active game; repeated phases and reconnects do not duplicate workers or session starts. Preserve existing crash reattachment and capture-gap logging.
- Resolve validated local settings, reviewed capture profile, pinned reader/assets and immutable data through existing APIs. No example fixture becomes production configuration. Missing/invalid settings, data, profile, names, model or platform produce an actionable unavailable status and leave dependent advice silent; capture/storage errors cannot silently kill the core's phase watcher.
- Persist original game-start data, patch, model, previous-patch and Engine-version identities and retain them across reconnect. Marshal capture results onto the event loop. Publish permitted Baseline/status updates through the existing Baseline boundary; Silent remains logging/status only. Provide a bounded snapshot handoff for final 44/45 consumers without importing Live or fabricating ranked advice.
- Refresh at startup, Lobby and game end only. Coalesce repeated triggers, serialize refresh jobs and prevent publication or mutation of an active game's pinned data. Retain qualified last-good data with visible rejection/failure reasons; use the integrated source-provenance contract.
- On a confirmed terminal phase, stop/join capture, close the pipeline and flush final media/fight/gap events before SessionStore.end_game. On process shutdown without confirmed outcome, flush available evidence and leave a reattachable game rather than fabricate placement/completion. Keep the completed game's mode/lock available to future review-job dispatch.
- Await cancelled watcher/tasks and supervise worker exceptions. Define a bounded graceful shutdown aligned with Electron's stop deadline. Real timeout/encoder/worker failures remain visible and recoverable; no forced Python exit, suppressed native errors or unreported media loss. Preserve existing shell restart/backoff and fresh launch-token security.
- Verify through actual temporary session/data stores, fixture external LCU/capture inputs, public process/localhost workflows and real existing capture/Baseline APIs: duplicate phases, reconnect, game identity, missing/invalid inputs, startup/Lobby/end refresh, active-game data pinning, worker errors, normal/forced shutdown and final event/media ordering. Keep real Windows/native-driver and target-latency evidence separate.
- Run relevant Python/UI/import/schema/generated-type/build checks, including public mode behavior without Live. Document the usable local configuration and lifecycle boundary; merge current integration before exact committed handoff and obtain a different merger agent.

## Remaining scope

Ticket 45 consumes this lifecycle for final Live/Engine worker integration, post-game subprocess jobs, harness start-run and numbering/block workflows, desktop shortcut/login settings and complete end-to-end verification. Ticket 44 owns delivered/displayed advice and review-ready transport/rendering. Ticket 49 owns real Windows/capture/recognition/device qualification. This prerequisite does not close those requirements or the parent specification.

## Implemented software boundary

The core now runs CaptureRuntime as the single session/capture owner, with safe-phase RefreshCoordinator scheduling and existing Baseline publication. [Runtime configuration and contracts](../docs/agents/runtime-boundary.md) document local settings, checked window title, real profile/name/glyph/model requirements, immutable original pins, latest-snapshot handoff and completed-game permissions. The worker persists gap-aware fight-history certificates in actual snapshots; confirmed PvP encounter times remain historical, and unknown/PvE rounds do not supply player-history coverage.

Positive identity is required throughout the lifecycle. Losing mode/game identity, client disappearance and an unconfirmed terminal phase stop capture, clear pending content and retain an unfinished original game. Public regressions reproduce both missing and different terminal identities. Matching positive reconnects reuse the original log/data/model/profile; only a confirmed matching terminal phase can end a successfully finalized session. Finished review permissions come from SessionStore, including Silent before and after start-run.

Shutdown gives capture eight seconds. Media has five seconds for flushing and at most one additional second for owned encoder cleanup/join; the shell allows ten seconds and explicitly warns before its child-termination fallback. Public regressions use a blocked native boundary, a real encoder that ignores termination and a real core process whose refresh is waiting on a slow local HTTP response. Timeouts and close failures remain visible and durable, and never synthesize game completion. Cancelling refresh no longer leaves a default-executor network worker holding process exit.

## Verification

After merging integration `5f0c6ad`, the full Python suite passed with cached pinned reader assets: **344 tests, no skips, 25.15 seconds, process exit 0**. Both existing Torch ONNX deprecation warnings remain. The suite includes actual CPU inference/training, RapidOCR and codec tests; a favorable exit does not establish the cause or resolution of ticket 50's historical native abort. The added runtime module has 36 public cases covering the real capture/storage/data/WebSocket/process workflows and external platform fixtures.

The UI passed **33 tests**, TypeScript checks, generated-type parity and production build. Import-linter retained both contracts; schema, frozen lock, scoped Ruff F821 and Git whitespace checks passed. A separate frozen sync without the Live package passed all **48 public runtime, process and Baseline cases** in 5.53 seconds with process exit 0. The Live package was then restored through frozen sync. The runtime documentation received a bounded Unslop pass: no wording changes were justified, and all 70 extracted constraints survived the preservation check.

## Qualification and integration limits

No owner API, real game, production data publication or Windows device run was performed. Missing production assets and rejected sources remain unavailable. Ticket 48 owns production qualification; ticket 49 owns Windows recognition/driver/latency checks; ticket 50 retains the unknown native-abort cause and final runtime gate. Tickets 44/45 must retain physical client bounds currently discarded by CapturedFrame, perform checked desktop DIP conversion and supply profile anchors before enabling overlays. This runtime leaves overlay permission false. Final Live dispatch, review jobs and run eligibility/numbering remain in ticket 45. This ticket stays open pending independent merger verification.


## Independent-review recovery correction

The merger reproduced a recovery blocker in `d039ff7`: after client loss successfully closed capture, storage retained the unfinished game and rejected every later game ID. The correction adds guarded `SessionStore.detach_game` and permits a different positively identified TFT game only after the previous capture thread has actually exited and joined, with successful finalization. Detach preserves the original unfinished log, pin, model and mode; it records no game_end or placement. Timed-out writers and failed close/flush still prevent release.

Public storage/runtime regressions exercise normal unknown loss followed by a new game with its own data pin/default mode, later reattachment to the original historical pin/Silent mode, failed-finalization and live-writer blocking, and queued old failures concurrent with the new game's first frame. The late-callback fixture confirms actual old-thread exit while the event loop is busy; removing only the callback-generation guard loses the new frame and fails, while the restored guard passes. Callback generation and pending-frame checks do not modify the capture log's original events or timestamps.

After integrating ticket 41 and root `13eaca5`, corrected full train verification passed **397 tests, no skips, 31.92 seconds, process exit 0**, with the same two Torch ONNX warnings. The public build without Live passed **61 runtime/storage/process/Baseline cases** in 6.59 seconds, exit 0; frozen sync restored Live afterward. UI verification passed **35 tests**, TypeScript, generated types and build. Both import contracts, schema, lock, scoped F821 and whitespace checks passed. The updated runtime document preserved all 72 extracted constraints in its bounded Unslop pass. The correction remains subject to independent merger review; no production, Windows or historical native-cause qualification is claimed.
