---
id: 34
title: Implement the TFT Assistant MVP spec
labels: [implementation:map]
status: open
assignee: codex
blocked_by: []
---

# Implement the TFT Assistant MVP spec

Source: [MVP spec](../docs/spec.md), its area files, and the resolved planning tickets 1–33. Integration branch: `implement/mvp`, based on `c521630`. Stage 1 is already in `main`; remaining work follows this dependency graph. The local tracker in [README](README.md) owns closure.

## Task graph

- [35: Durable sessions and crash-safe game logs](035-session-log.md); blocked by nothing.
- [36: Validated patch data and immutable refresh snapshots](036-data-layer.md); blocked by nothing.
- [37: Automatic screen capture and purchase tracking](037-capture-pipeline.md); blocked by [47, 38].
- [38: Own-board recognition and crop training](038-board-reader-training.md); blocked by [47].
- [39: Board power, classification and trait-only opponent inference](039-board-power-opponents.md); blocked by [46].
- [40: Game plan, transitions and seeded Line simulation](040-game-plan-lines.md); blocked by [39, 50].
- [41: Shop, Wisp, item, augment, carousel and positioning advice](041-decision-sub-engines.md); blocked by [40].
- [42: Replay, post-game review and evaluation harness](042-replay-review-harness.md); blocked by [35, 41].
- [43: Baseline Guides and permitted hints](043-baseline-surfaces.md); blocked by [36, 39].
- [44: Separable Live advisor, overlay, cockpit and voice](044-live-surfaces.md); blocked by [37, 41, 43].
- [45: End-to-end runtime, refresh/review jobs and run workflows](045-runtime-run.md); blocked by [38, 42, 44, 50].

- [46: Immutable data contracts and capture name lists](046-data-contracts.md); blocked by nothing.
- [47: Capture transport, OCR, tracking and visual-reader contract](047-capture-contracts.md); blocked by [35, 46].
- [48: First sourced patch-data candidate and qualification](048-production-data-readiness.md); blocked by [36, 40, 41].
- [49: Recognition, capture and target hardware qualification](049-capture-device-qualification.md); blocked by [37, 38, 40, 45].
- [50: Native macOS teardown abort after the full Python suite](050-native-test-teardown.md); blocked by nothing.

## Decisions so far

- 2026-10-11: Corrected ticket 40 merged in `33b83b1`. All 191 Python assertions pass, but the process aborts during native shutdown. Ticket 50 retains this blocking verification failure; ticket 37 continues independently. A passing subset or macOS software check does not qualify Windows/live capture.

- 2026-10-10: [Ticket 38](038-board-reader-training.md) is closed after reader merge `5a74f06` and promotion fix merge `c833058`. Combined verification passed 154 Python tests with the offline training group, 31 UI tests and all import/schema/lock/type/build gates. Qualification remains in ticket 49. Full capture ticket 37 is now unblocked and resumes on a fresh branch from the integration tip.

- 2026-10-10: [Ticket 43](043-baseline-surfaces.md) integrated in `19e28abe` and its software boundary is closed. Combined verification passed 148 Python tests with the offline training group, 31 UI tests and the import/schema/lock/type/build gates. The [Baseline boundary](../docs/agents/baseline-boundary.md) supplies the interfaces for tickets 44 and 45; production data and Windows/device qualification remain in tickets 48 and 49. Reader ticket 38 is also integrated but remains open while promotion review fixes are completed.

- 2026-10-10: Ticket 49 retains owner-data and Windows/device qualification after the reader, capture and planning software boundaries. Passing macOS software tests does not close those conditions or this parent specification.

- 2026-10-07: Ticket 36's software boundary closed after merge `b2bcc3e` and 122 Python/26 UI integration tests. Production data preparation and qualification remain open in ticket 48; no current rules, fits or live calendar were fabricated.

- 2026-10-07: [Ticket 36](036-data-layer.md) software boundary integrated in `b2bcc3e`; 122 Python tests, 26 UI tests, import/schema/type checks, lock validation and data Ruff checks passed. Ticket 36 remains open for reviewed production bootstrap and source qualification; current static tables, fits and patch calendar are not fulfilled by fixtures.

- 2026-10-07: [Ticket 47](047-capture-contracts.md) closed after merge `4414d29`; the capture and visual-reader contract passed 107 Python tests, 26 UI tests, import/schema/type checks and lock validation. Reader integration remains in open tickets 38 and 37; Windows and live-game qualification remain separate.

- 2026-10-06: Stage 1 verified in current `main`; Vault state predates its merge.
- 2026-10-06: Owner approved public test seams. Runtime checks on Windows remain distinct from macOS verification.
- 2026-10-06: [Ticket 46](046-data-contracts.md) closed after merge `dfa6be8`; immutable data contracts and capture name/icon lists passed 59 macOS integration tests, both import contracts, and schema drift verification. Full data workflows remain in open ticket 36.
- 2026-10-06: [Ticket 35](035-session-log.md) closed after merge `0a86dcd`; durable sessions and game logs passed 72 Python tests, 26 UI tests, import/schema/type checks, and the UI production build on macOS. Windows and live-game checks remain separate.
- 2026-10-06: [Ticket 39](039-board-power-opponents.md) closed after merge `27a6028`; board and trait-only opponent APIs passed 91 Python tests and 26 UI tests plus import/schema/type checks. Contract pointers are in `docs/agents/engine-contracts.md`; actual roster performance and statistical fits remain unqualified.

## Comments

### 2026-10-06 — codex

Ticket 46 extracts the verified contract/name-list prerequisite from ticket 36. Capture and Engine depend on 46; full data refresh and Baseline Guides remain dependent on 36.
