---
id: 44
title: Separable Live advisor, overlay, cockpit and voice
labels: [implementation:task]
status: open
assignee: codex-live-surfaces
parent: 34
blocked_by: [37, 41, 43]
---

# Separable Live advisor, overlay, cockpit and voice

## Sources

- [docs/spec/runtime.md](../docs/spec/runtime.md)
- [docs/spec/surfaces.md](../docs/spec/surfaces.md)

## Acceptance

Live advisor package and UI module separable, versioned messages, ranked advice surfaces/anchors/tooltips/limited overlay input, cockpit/projections/opponents/roll tracker/pins, freshness/paused/fullscreen/restart handling, voice rules, shown-advice/latency events and review UI.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

### 2026-10-11 — Replay attribution prerequisite

Ticket 42 preflight found that current `SurfaceShown`/`ui_show` events contain only surface, content ID and mode. A Baseline content ID is a render revision; it does not identify an advice decision or its options. Persist a versioned delivered-advice record and map each actual surface acknowledgement to its stable decision/option IDs. Followed/ignored status and follow rate must use confirmed display events, never Engine generation alone. Record delivery and display times separately for latency and stale/too-late analysis; keep Silent and mode-boundary enforcement intact.

### 2026-10-12 — Transport and desktop geometry integration

The bounded implementation notes are `/tmp/tft-assistant-44-transport-notes.md`. Ticket 41's candidate benchmark retains 17,741,188 bytes of full Advice/Line evidence. Preserve full raw scores and paired distributions for offline review, but implement bounded summary/reference delivery, validated revision/mode membership, paged detail requests, awaited sends and coalesced latest state. WebSocket incoming-message limits do not bound outgoing evidence. Treat the note's proposed message budgets as unmeasured design choices; qualify the implemented byte/memory/latency behavior rather than call those values specification limits.

Ticket 53 currently keeps `overlay_allowed=false` when real desktop geometry is unavailable. `WindowsCaptureSource._window` reads physical client bounds, but `CapturedFrame` does not expose them to runtime consumers. Wire positively observed client origin/size, the correct physical-pixel-to-Electron-DIP conversion and reviewed profile anchors through the capture/publication boundary. Clear or hide overlay content on stale geometry, window loss, incompatible fullscreen, restart or mode downgrade. Do not invent a desktop origin or assume one scale factor for mixed-DPI displays. Mac fixture rendering is separate from actual Windows geometry, overlay exclusion and driver qualification in ticket 49.

### 2026-10-12 — Independently integrated shared evidence slice

The pure `tft_engine.evidence.EvidenceGraph` boundary and four public graph regressions are independently integrated as `a67bcd2381ef3c7859e2dd491bac769b62898120` from exact `58ce2b66a4d3c1132cdf6f9a67704cf06177a9d4`. The separate reviewer checked lossless canonical finite JSON, reserved-key escaping, authenticated root-member paths, immutable records, unrelated-branch isolation, full corruption rejection and bounded UTF-8/container pages. Merged-root graph and frozen-replay checks passed 31 tests in 4.15 seconds, process exit 0; both import contracts, schema, lock and whitespace checks passed. Ticket 42 can consume this committed helper without importing Live.

This is a shared software slice only. Delivery membership/modes, persistence, UI surfaces, geometry, actual display/voice acknowledgement and the remainder of this ticket stay open. The helper preserves full offline values; these focused checks do not qualify full-game memory, live latency or target-device behavior.

### 2026-10-14 — Recovered Live core checkpoint

The original author session stopped at its usage limit with the Live/runtime core interfaces committed as exact `f9faee21a3924c29727fcdfbc3bf8f06057148e9` and two uncommitted core files. This recovery copied only the `core/src/tft_core/storage.py` and `core/tests/test_review_transport.py` diffs onto branch `implement/live-core-recovery` from that exact commit, then merged integration tips `2506b6c` and `fd374c8`. The shared per-root OS store lock, unique SQLite rebuild files, one-second acquisition deadline and stale-sequence correction remain intact. The author worktree, its UI and dependency drafts, stashes and `.DS_Store` were left unchanged.

Three core findings were fixed through public seams, each with a failing regression first.

- Review tags now serialize through a per-game OS lock shared by every process (`reviews/.GAME.tags.lock`, same bounded one-second acquisition), not a per-instance thread lock. The native tag flush runs outside the store lock. Under the store lock, the staged replacement is rejected after a Silent game starts, the review becomes locked, the report is replaced or the tag bytes change. Red: a second process tagging a different decision lost its write with `Review or tags changed; reload before retrying`. Green: both tags persist after the held flush is released. The authenticated socket still answers a Silent downgrade in under 0.5 seconds while a tag flush is blocked, and the staged tag returns an error.
- `OwnedIO.close` wakes idle workers with sentinels instead of racing their 50 ms poll. It cancels discarded and late-admitted requests, and a natively blocked worker stays daemon-owned without late publication. Red: ten real-process shutdowns at a 10 ms bound reported `alive_workers` 2 instead of 1, and the existing 50 ms process test also failed on that run. Green: ten of ten report one remaining blocked worker, with no delivery or evidence events. The expected blocked-worker count and the native-block fixture are unchanged.
- `LiveDeliveryController.clear` now appends one `session_controls_reset` event when it drops an accepted pin while the pinned game still owns the log. This covers capture pauses, mode suppression, epoch clears and shutdown. The payload carries `schema_version`, `game_id`, `data_snapshot_id`, `delivery_revision`, the accepted `line_pin` sequence as `pin_seq`, its receipt time as `pin_read_at`, and `reason`. The event uses append time and does not alter snapshot or pin timestamps. A clear without a pin writes nothing; a detached or replaced game relies on its own logged boundary. A failed write still clears the in-memory pin and reports `pin reset could not be logged` in the Live status. The writer shape was taken from the held ticket 42 reader by source reading only. After `fd374c8` integrated that reader, the regression also projects the actual log through `project_session_controls`: the pin applies after `line_pin` and is gone at this reset's sequence.

Verification on macOS at the merged source: the focused storage, process, transport, delivery, shutdown, server, runtime, worker, message, package, geometry and session-control suites passed 142 tests. With `tft-live` actually uninstalled, the non-Live suites passed 121 tests; the only failure is `test_package_imports[tft_live]`, as expected, and the Live delivery tests require the package. The Live and train groups were then restored. The full frozen train suite with the cached CPU reader models and portable PowerShell 7.5.3 passed 648 tests without skips in 99.16 seconds, process exit 0, with the two existing Torch ONNX-export warnings. An earlier full run before the `fd374c8` merge passed 626 tests in 110.90 seconds. Import contracts (2 kept), the schema check, the lock check, scoped F821 and the whitespace diff check passed. The UI passed the generated-type check, typecheck, 37 tests and build after `npm ci`; UI and message sources are unchanged by this recovery.

This remains a core checkpoint for independent review and merge, not acceptance of this ticket. The full application UI (cockpit, overlay, review, voice and geometry surfaces), measured message and resource budgets, Windows lock/rename and display/overlay behavior, and the historical native teardown cause remain open. No owner assets, client, credentials, matches or measurement runs were accessed.

### 2026-10-14 — Independent review of the recovered Live core checkpoint

A separate reviewer inspected the full core checkpoint from integration `9a05bf8cf01993be04c3d445e8fcdc3b48434ad2` to exact `e3d4a6c70ca1b94042a00598d12eb223e8225b92`, not only the three recovery fixes. The review covered the optional `LiveAdvisor` boundary, delivery preparation, persistence and activation, `EvidenceGraph` paging and wire integers, authenticated modes and membership, the per-client writer and review queues, owned I/O and shutdown, runtime hooks, message schemas and generated types, capture geometry, the per-game tag lock and the pin reset event. The checkpoint was accepted and merged with `--no-ff` into a reviewer worktree started from `9a05bf8`; the merged tree is identical to `e3d4a6c`.

Checks on macOS at the merged source:

- The focused storage, process, transport, delivery, shutdown, server, runtime, message, package, geometry, session-control, capture-pipeline and evidence-graph suites passed 161 tests in 38.56 seconds.
- The real-process shutdown test, the cross-process and staged tag tests, the review transport suite and the four pin-reset cases were repeated five times. Each run passed all 21 tests.
- With `tft-live` physically uninstalled from the reviewer environment, the core suites passed 140 tests without skips; only the intentional `test_package_imports[tft_live]` was deselected. Run separately, it failed as expected. The Live and train groups were then restored.
- A post-close `OwnedIO.call` raises `Core I/O is closed` rather than a bare cancellation.
- Import contracts (2 kept), the schema check, the lock check, F821 over `src`, `packages` and `tests`, and the whitespace check passed. The UI passed `npm ci`, the generated-type check, typecheck, 37 tests and build. The UI sources are those of the held `f9faee2` interface baseline; the active ticket 44 UI draft is not included.

The full frozen train suite was not repeated, because the reviewed tree is unchanged from the author's 648-test run.

Non-blocking observations remain for later ticket 44 work. The per-client writer coalesces pending broadcasts by message type, so under backpressure a later `error` broadcast can replace an earlier unsent one. A mode change that arrives through the gameflow path does not immediately republish Live or geometry state; the next runtime geometry publication corrects geometry clients. When the pin reset cannot be logged, the in-memory pin is cleared and the failure is visible in Live status, but replay keeps projecting the logged pin until a later boundary. The unused `canonical_bytes` import in `live_delivery.py` from `f9faee2` remains.

This is a bounded and explicitly partial core slice. Ticket 44 stays open: the application UI and the accepted review-section integration, measured message and resource budgets, Windows lock and rename behavior, display and overlay geometry, voice, and the historical native teardown cause are not addressed here. Runtime Engine jobs in ticket 55 remain held. Production (48), Windows (49) and native (50) qualification and ticket 45 remain unqualified. No owner assets, credentials, client access or matches were used.

### 2026-10-14 — Recovered Live UI and typed review sections

The original UI session stopped at its usage limit with its work uncommitted in `worktrees/ticket-44` on `f9faee21a3924c29727fcdfbc3bf8f06057148e9`. Branch `implement/live-ui-recovery` (worktree `worktrees/live-ui-recovery`) starts from that commit. Its first commit, `eed2746`, copies only the dirty tracked `ui/` diff and the 24 named untracked `ui/` source, test and fixture files. Before and after the copy, the status list, the full diff hash (`f0c98f7c…`), every untracked file hash and the stash list in the author worktree matched exactly. No `node_modules` or core files were copied. The branch then merged the review-section helper `implement/review-sections-ui` (`2617d4b`, containing `ec1f6ca`), integration `9a05bf8` and, last, integration `251502a`, which brings in the reviewed Live core checkpoint. That final merge was clean, and the core and schema trees are identical to `251502a`. The `jsdom` ^30.1.2 dependency from the original draft is part of the package and lock.

Changes, each built red then green through the approved renderer seams:

- `ReviewPanel` mounts `ReviewSection` only on the typed paths `['surface', name]` for the Game plan, Lines, Fights, Full timeline and Positioning. The section request issues only `page` operations with a typed path, cursor and limit; a compile-time check shows the existing `ReviewRequest` remains assignable to it. Raw evidence opens only through an explicit Debug action (a row's Debug button or the Debug tab). The `scopeKey` combines the game, the immutable `report_id`, `evidence_id` and a mode/connection epoch. As a result, loaded pages survive parent rerenders with new inline callbacks, and any mode change discards them. Two mutation checks confirmed the tests: removing `scopeKey` and removing the epoch each made the matching test fail.
- The normal sections now render the producer's typed fields. The Game plan shows the target, backup, candidates, open or committed status, pivots, the rejected target, the player comp and its divergence, and the called status. Fights show the pre-fight forecast (win chance and predicted HP loss) beside the observed result and HP lost. When a forecast is missing, the section names the reason. The timeline shows the Engine decision ID, the signed cost with its paired uncertainty or the reason it has none, a close call, and the shown status. Positioning lists the advised layout per unit with its confidence. Lines show each schedule's level-ups and roll-down floors, the hit and death chances, the death placement cost and the confidence, next to the existing charts on common scales.
- Live cockpit: a banner names each stale field and how long it has been unread. The Game plan lists candidates and a called pivot. Every candidate Line shows its schedule, hit chance and death chance. On the overlay, the amber Line chip now names the Line that beats the pin and the size of its gain.

Producer gaps recorded instead of invented. The ticket 42 review surface stores the pinned Line only as its schedule, with no projection, so the UI shows that schedule and states "Pinned forecast unavailable". The `timeline` section contains no capture-gap rows; the UI says so and points to the gaps under Debug. Called status, shown status and positioning follow/result attribution remain `display_attribution_unavailable` in the producer, and the UI displays that value as recorded. A typed "what disagrees" field for low-confidence Live advice is not rendered, because no producer field has been confirmed.

Verification on macOS at merged tip `2bdfb61`: `npm ci` passed, along with 20 files and 80 Vitest tests, typecheck, the generated-type check and `electron-vite build`. Rendered QA used a T3 browser preview of the renderer fixture on its own port, 5191. The fixture serves synthetic typed sections in the producer's shapes and is labelled synthetic. In Chromium, all five sections rendered, Lines drew two SVG charts plus the pinned schedule, no raw `<pre>` appeared before an explicit Debug action, and Debug then opened `lines / 0`. The Live cockpit showed the candidates and every Line schedule, with no horizontal overflow at 1280 px. The screenshots are under `~/.t3/userdata/browser-artifacts/`. The helper fixture server on port 5182 was not touched.

Ticket 44 stays open. Still missing: Electron main-process and IPC behavior in a real Electron run; Windows desktop geometry, overlay exclusion, OneCore voice and display qualification (49); measured message, latency and resource budgets; final core Live integration and the runtime jobs held in 55; and the core reviewer's non-blocking observations. Fixture results are not live results. This branch needs a separate reviewer and merger.


### 2026-10-15 — GPT-6.1 Sol review corrections

Different review of held UI `778d0a1` reproduced five defects: Live post-game review remounted and closed itself; the Line widget inherited disabled pointer events; roll-tracker values remained visible after ownership/econ expiry in both surfaces; positioning arrows outlived their advice deadline; and the evidence drawer ignored a newly selected path in the same revision. No source from that held checkpoint was merged.

The isolated `implement/live-ui-sol-fixes` correction keeps ReviewPanel at one React tree position, enables pointer input only on the Line widget, hides stale overlay/cockpit tracker values, applies advice validity to movement arrows and scopes evidence navigation by game/revision/selected path. Six public renderer regressions reproduce the failures and pass after these changes. The browser fixture now exposes a Live EndOfGame state for this case.

Full UI verification passed 86 tests across 21 files. Generated types, typecheck and Electron build passed. Initial typecheck found two test-fixture array nullability errors; nonnull fixture assertions corrected them. The computed-style test initially used a raw CSS import that did not establish the real stylesheet in this runner; reading the package-local stylesheet reproduced inherited pointer-events:none before the fix. A fixture evaluation before reload also reported the new fixture function missing; navigation reloaded the updated module.

T3 browser QA on the actual mounted App at synthetic Live EndOfGame confirmed that opening Post-game review leaves Logged games visible, replaces the cockpit and produces no horizontal overflow at 1280 pixels. Screenshot: `/Users/vankata/.t3/userdata/browser-artifacts/browser-screenshot-127-0-0-1-mv97hj9g-4fc67d10.png`. This is renderer-fixture evidence, not Electron main/IPC, Windows overlay input, capture or live-game qualification. Corrected source still requires different review and merger integration; full44/55 and remaining producers remain open.
