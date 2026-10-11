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
