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

The original author session stopped at its usage limit with the Live/runtime core interfaces committed as exact `f9faee21a3924c29727fcdfbc3bf8f06057148e9` and two uncommitted core files. This recovery copied only the `core/src/tft_core/storage.py` and `core/tests/test_review_transport.py` diffs onto branch `implement/live-core-recovery` from that exact commit, then merged integration tip `2506b6c`. The shared per-root OS store lock, unique SQLite rebuild files, one-second acquisition deadline and stale-sequence correction remain intact. The author worktree, its UI and dependency drafts, stashes and `.DS_Store` were left unchanged.

Three core findings were fixed through public seams, each with a failing regression first.

- Review tags now serialize through a per-game OS lock shared by every process (`reviews/.GAME.tags.lock`, same bounded one-second acquisition), not a per-instance thread lock. The native tag flush runs outside the store lock. Under the store lock, the staged replacement is rejected after a Silent game starts, the review becomes locked, the report is replaced or the tag bytes change. Red: a second process tagging a different decision lost its write with `Review or tags changed; reload before retrying`. Green: both tags persist after the held flush is released. The authenticated socket still answers a Silent downgrade in under 0.5 seconds while a tag flush is blocked, and the staged tag returns an error.
- `OwnedIO.close` wakes idle workers with sentinels instead of racing their 50 ms poll. It cancels discarded and late-admitted requests, and a natively blocked worker stays daemon-owned without late publication. Red: ten real-process shutdowns at a 10 ms bound reported `alive_workers` 2 instead of 1, and the existing 50 ms process test also failed on that run. Green: ten of ten report one remaining blocked worker, with no delivery or evidence events. The expected blocked-worker count and the native-block fixture are unchanged.
- `LiveDeliveryController.clear` now appends one `session_controls_reset` event when it drops an accepted pin while the pinned game still owns the log. This covers capture pauses, mode suppression, epoch clears and shutdown. The payload carries `schema_version`, `game_id`, `data_snapshot_id`, `delivery_revision`, the accepted `line_pin` sequence as `pin_seq`, its receipt time as `pin_read_at`, and `reason`. The event uses append time and does not alter snapshot or pin timestamps. A clear without a pin writes nothing; a detached or replaced game relies on its own logged boundary. A failed write still clears the in-memory pin and reports `pin reset could not be logged` in the Live status. This shape matches the ticket 42 reader's `session_controls_reset` game/data validation by source reading only; no ticket 42 edits were imported.

Verification on macOS: the focused storage, process, transport, delivery, shutdown, server, runtime, worker, message, package and geometry suites passed 120 tests. With `tft-live` actually uninstalled, the non-Live suites passed 99 tests; the only failure is `test_package_imports[tft_live]`, and every Live delivery test fails with `ModuleNotFoundError: No module named 'tft_live'`, as expected. The Live and train groups were then restored. The full frozen train suite with the cached CPU reader models and portable PowerShell 7.5.3 passed 626 tests without skips in 110.90 seconds, process exit 0, with the two existing Torch ONNX-export warnings. Import contracts (2 kept), the schema check, the lock check, scoped F821 and the whitespace diff check passed. The UI passed the generated-type check, typecheck, 37 tests and build after `npm ci`.

This remains a core checkpoint for independent review and merge, not acceptance of this ticket. The full application UI (cockpit, overlay, review, voice and geometry surfaces), measured message and resource budgets, Windows lock/rename and display/overlay behavior, and the historical native teardown cause remain open. No owner assets, client, credentials, matches or measurement runs were accessed.
