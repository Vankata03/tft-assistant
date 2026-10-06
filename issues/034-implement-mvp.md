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
- [37: Automatic screen capture and purchase tracking](037-capture-pipeline.md); blocked by [35, 46].
- [38: Own-board recognition and crop training](038-board-reader-training.md); blocked by [37].
- [39: Board power, classification and trait-only opponent inference](039-board-power-opponents.md); blocked by [46].
- [40: Game plan, transitions and seeded Line simulation](040-game-plan-lines.md); blocked by [39].
- [41: Shop, Wisp, item, augment, carousel and positioning advice](041-decision-sub-engines.md); blocked by [40].
- [42: Replay, post-game review and evaluation harness](042-replay-review-harness.md); blocked by [35, 41].
- [43: Baseline Guides and permitted hints](043-baseline-surfaces.md); blocked by [36, 39].
- [44: Separable Live advisor, overlay, cockpit and voice](044-live-surfaces.md); blocked by [37, 41, 43].
- [45: End-to-end runtime, refresh/review jobs and run workflows](045-runtime-run.md); blocked by [38, 42, 44].

- [46: Immutable data contracts and capture name lists](046-data-contracts.md); blocked by nothing.

## Decisions so far

- 2026-10-06: Stage 1 verified in current `main`; Vault state predates its merge.
- 2026-10-06: Owner approved public test seams. Runtime checks on Windows remain distinct from macOS verification.
- 2026-10-06: [Ticket 46](046-data-contracts.md) closed after merge `dfa6be8`; immutable data contracts and capture name/icon lists passed 59 macOS integration tests, both import contracts, and schema drift verification. Full data workflows remain in open ticket 36.
- 2026-10-06: [Ticket 35](035-session-log.md) closed after merge `0a86dcd`; durable sessions and game logs passed 72 Python tests, 26 UI tests, import/schema/type checks, and the UI production build on macOS. Windows and live-game checks remain separate.
- 2026-10-06: [Ticket 39](039-board-power-opponents.md) closed after merge `27a6028`; board and trait-only opponent APIs passed 91 Python tests and 26 UI tests plus import/schema/type checks. Contract pointers are in `docs/agents/engine-contracts.md`; actual roster performance and statistical fits remain unqualified.

## Comments

### 2026-10-06 — codex

Ticket 46 extracts the verified contract/name-list prerequisite from ticket 36. Capture and Engine depend on 46; full data refresh and Baseline Guides remain dependent on 36.
