---
id: 55
title: Complete Engine, Live, review-job and launcher runtime software
labels: [implementation:task]
status: open
assignee:
parent: 34
blocked_by: [38, 42, 44, 53, 54, 56, 57]
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

### 2026-10-13 — Independent Windows test handoff

Ticket 57 extracts the build-first launcher and operator instructions requested for tonight's Windows tests. This ticket retains optional login/shortcut settings and all final runtime requirements; a platform handoff does not qualify Live/data/model behavior. The owner explicitly authorized committing and pushing verified integration work.


## Comments

### 2026-10-14 — Isolated actual-app runtime proof

- The interrupted runtime recovery is preserved at `3f2fa0a`. Root copied only its unfinished public app test into `implement/runtime-app-proof`, reconciled current `dea8085`, and replaced diagnostic print-only probes with assertions through the actual app, authenticated WebSocket, durable session API and real review child. Original runtime and UI recovery worktrees were not modified.
- The source-gated Live publication case fails against pushed root `dea8085` with no Engine delivery after eight seconds, and passes on the candidate runtime. The fixture lacks validated Guides, board and inventory inputs, so the real Engine returns paused advice; this is wiring proof, not useful recommendation or asset qualification. Silent downgrade clears content, and an in-game upgrade is rejected.
- A confirmed end finalizes the log before the actual child publishes a review-ready receipt; authenticated summary access matches its report identity, and missing placement remains null. Positive TFT phase with missing settings reports the exact setup path, opens no capture device, preserves data and still enforces mode guards. The latter case runs with and without the advisor capability.
- At source `80be282`, the full frozen training suite passed 667 without skips in 103.80 seconds, process 0, with two existing Torch export warnings. This predates the final additional capability parameter case. Final app tests pass four cases in 1.35 seconds. With Live actually uninstalled and import absence checked, the runtime/Engine/jobs/lease/desktop and no-advisor app set passed 61 in 10.95 seconds; Live/train were restored. Imports kept both contracts, schemas, frozen lock, F821 and whitespace passed.
- The inherited diagnostic probe initially timed out without a confirmed cause. Early test-only assertions used a nonexistent storage method, an absent gameflow field and the wrong error code; they were corrected to the existing public interfaces. Permanent tests wait for reported Lobby before selecting a session mode. No production fix is claimed for that initial diagnostic timeout.
- Independent UI/runtime review remains unavailable: Claude returned an API rate limit, Antigravity could not open a session, and OpenCode rejected free-tier use through this provider. The UI source is held at `778d0a1`. This runtime branch is a checked partial candidate, not independently accepted or merged; no push or ticket closure is claimed. Full UI, remaining harness/run workflows, runtime resources, production inputs, Windows/live-game behavior and historical native causality remain open.
