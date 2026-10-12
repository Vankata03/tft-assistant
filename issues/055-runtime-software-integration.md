---
id: 55
title: Complete Engine, Live, review-job and launcher runtime software
labels: [implementation:task]
status: open
assignee:
parent: 34
blocked_by: [38, 42, 44, 53, 54, 56]
---

# Complete Engine, Live, review-job and launcher runtime software

This extracts the remaining independently implementable software from [ticket 45](045-runtime-run.md). Ticket 45 retains final runtime qualification and the unresolved historical native gate in 50. No requirement is removed: the canonical runtime, review/harness, surfaces and patch-workflow specifications still apply. Windows/client/model/device qualification remains 49; production data remains 48.

## Sources

- [Runtime specification](../docs/spec/runtime.md), [review and harness](../docs/spec/review-and-harness.md), [surfaces](../docs/spec/surfaces.md) and [patch workflow](../docs/spec/patch-workflow.md).
- [Ticket 45](045-runtime-run.md) and its attribution, shutdown and lifecycle comments.
- Integrated [capture runtime boundary](../docs/agents/runtime-boundary.md), [replay boundary](../docs/agents/replay-boundary.md), [decision contracts](../docs/agents/decision-contracts.md) and [approved public seams](../docs/agents/implementation.md).
- Preparation: `/tmp/tft-assistant-45-preflight.md`. Reconcile its dated pointers with the final 42/44/54 APIs before implementation.

## Acceptance

- Consume the single CaptureRuntime lifecycle from 53. Run Engine work on a separate thread with bounded latest-snapshot delivery. Preserve game/data/model identities, field timestamps and source evidence. Reject delayed results after detach, failure, mode downgrade, restart or shutdown; expensive evaluation must not create an unbounded capture or callback queue.
- Load the optional Live package only for installed Live sessions. Wire the final 44 publication, pin/detail commands, actual display/voice acknowledgements and delivery/latency events. Silent remains logging/status only; Baseline uses the strict Engine allowlist. Verify the actual process/public UI build with Live omitted.
- Keep refresh serialized at qualified safe lifecycle points through 53, with immutable original game pins and visible last-good/rejection status. Engine or review initialization failures cannot release an active-game publication guard.
- On confirmed game completion, finalize capture/media before the session end, then dispatch the actual 42 review worker as a below-normal-priority subprocess. Deduplicate each game/version/data job, bound concurrency, retain durable completion/error state and announce only a successfully stored review. The completed game's authoritative lock governs notifications/detail access even after the next game starts. Missing placement/EOG/API truth stays unavailable.
- Supervise capture, Engine, watcher, refresh and owned review jobs through the actual core process. Await cancellation, bound shutdown within the shell contract, and retain visible timeout/incomplete-evidence errors. Do not force Python exit, suppress native errors, skip assertions or describe interrupted work as successfully flushed. Preserve launch-token isolation and shell restart/backoff.
- Integrate the explicit one-shot `tft-harness start-run` workflow from 42, including refreshed and frozen exactly-50 qualified no-coach matches, authoritative lock release, finished ranked/current-set Live numbering and complete ten-game blocks. Do not schedule eval, fit, training or start-run. Do not run the owner's workflow in this implementation session.
- Provide a working repository build/start launcher, a no-console desktop-shortcut workflow and the optional start-at-login setting. Validate settings without breaking the strict capture TOML. Keep host-specific paths in local preferences; do not create a shortcut or change login startup on this host as Windows evidence. Preserve command failure status.
- Verify through actual temporary stores, fixture external LCU/window/outcome inputs, authenticated localhost WebSockets and real core/review child processes: normal start/end, duplicates, reconnect/detach, slow Engine, stale callbacks, mode changes, unavailable assets/data, review success/failure/lock, safe refresh and normal/forced shutdown. Run appropriate Python/UI/import/schema/lock/generated-type/build gates and document configuration, commands and failure recovery.
- Merge the latest integration tip before exact committed handoff and obtain a different merger. Preserve the open production, Windows/device and historical native-cause qualification conditions; favorable process exits do not establish a causal repair for 50.

## Qualification boundary

Fixture/API-adapter tests do not qualify the actual Windows EOG endpoint or match-ID join, recognition accuracy, WGC/BitBlt/DPI/fullscreen behavior, OneCore voice, overlay exclusion or the Ryzen/game-running latency budget. Ticket 49 retains those checks. The historical exit-134 cause remains unresolved in 50 and blocks final runtime ticket 45 and the parent MVP even when this software boundary passes.
