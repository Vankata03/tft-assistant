---
id: 45
title: End-to-end runtime, refresh/review jobs and run workflows
labels: [implementation:task]
status: open
assignee:
parent: 34
blocked_by: [50, 55]
---

# End-to-end runtime, refresh/review jobs and run workflows

## Sources

- [docs/spec/runtime.md](../docs/spec/runtime.md)
- [docs/spec/review-and-harness.md](../docs/spec/review-and-harness.md)
- [docs/spec/patch-workflow.md](../docs/spec/patch-workflow.md)

## Acceptance

Wire capture/Engine threads and persistent sessions to supervised core, data refresh at safe lifecycle points, below-normal post-game jobs, baseline refresh and explicit start-run CLI freeze/unlock/numbering/blocks, shortcut/login settings, integration verification and operator documentation. Do not start the owner's run or claim completion of 50 human-played games.

The independently implementable software is tracked in [ticket 55](055-runtime-software-integration.md), after the capture lifecycle prerequisite in 53. This ticket remains open until that software is independently integrated and its final runtime qualification gate in 50 is fulfilled. Windows/client/model/device qualification remains 49. Splitting the software work does not waive any referenced acceptance condition.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

### 2026-10-11 — Delivered versus shown advice

Runtime wiring must preserve ticket 44's delivered-advice and surface-acknowledgement mapping for replay. Engine evaluation is not evidence that advice was shown. Unknown or absent acknowledgement remains unavailable; replay never fabricates an ignored advice event from a generated recommendation.

Capture shutdown must precede `SessionStore.end_game`: stop/join the runner, close its pipeline and flush final media/fight/gap events while the game is still active, then end the session and launch review. Current `CoreServer.publish_gameflow` ends sessions synchronously for terminal phases; runtime wiring must account for that ordering. Delayed review-ready notifications use the completed game's mode and review lock, not a later next-session default.

### 2026-10-11 — Runtime lifecycle preflight

Read-only implementation preparation is saved at `/tmp/tft-assistant-45-preflight.md`, based on integration `8e3c406`. Core startup currently wires only the session server and LCU watcher; capture, Engine, safe refresh and review jobs still need a single lifecycle owner. Marshal thread results to the event loop, coalesce repeated phase triggers and preserve each game's pinned data/model identity.

The shell's current three-second graceful-stop deadline can expire before capture media finishes flushing. Align it with a bounded core shutdown contract; test final log/media ordering through the public process/session boundary. A forced timeout must remain visible as a failure or gap rather than a successful flush. This preparation does not implement runtime behavior or close ticket 50's historical native failure.

### 2026-10-11 — Capture lifecycle prerequisite extracted

Ticket 53 implements the serialized capture/session/data lifecycle through the already closed software boundaries. This allows concrete runtime wiring before full Live surfaces and replay finish. This ticket retains final Live/Engine dispatch, review jobs, run workflows and complete runtime verification; ticket 50 remains its historical native qualification gate.

### 2026-10-12 — Final software work separated from historical qualification

Ticket 53 is independently integrated and closed. Ticket 55 now owns the remaining Engine/Live dispatch, supervised review jobs, run workflows, launcher/settings and end-to-end software verification after 42/44/54. Ticket 50 still has no minimized red-capable abort or verified causal repair; keeping it as this ticket's final qualification gate must not prevent implementation of those independent software requirements. This ticket and the parent remain open until their full conditions are fulfilled.
