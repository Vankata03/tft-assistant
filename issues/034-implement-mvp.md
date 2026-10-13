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
- [40: Game plan, transitions and seeded Line simulation](040-game-plan-lines.md); blocked by [39].
- [41: Shop, Wisp, item, augment, carousel and positioning advice](041-decision-sub-engines.md); blocked by [40].
- [42: Replay, post-game review and evaluation harness](042-replay-review-harness.md); blocked by [35, 41, 52].
- [43: Baseline Guides and permitted hints](043-baseline-surfaces.md); blocked by [36, 39].
- [44: Separable Live advisor, overlay, cockpit and voice](044-live-surfaces.md); blocked by [37, 41, 43].
- [45: End-to-end runtime, refresh/review jobs and run workflows](045-runtime-run.md); blocked by [50, 55].

- [46: Immutable data contracts and capture name lists](046-data-contracts.md); blocked by nothing.
- [47: Capture transport, OCR, tracking and visual-reader contract](047-capture-contracts.md); blocked by [35, 46].
- [48: First sourced patch-data candidate and qualification](048-production-data-readiness.md); blocked by [36, 40, 41, 51, 54, 56].
- [49: Recognition, capture and target hardware qualification](049-capture-device-qualification.md); blocked by [37, 38, 40, 55].
- [50: Native macOS teardown abort after the full Python suite](050-native-test-teardown.md); blocked by nothing.
- [51: Preserve source-owned publication and cohort provenance](051-source-provenance.md); blocked by [36].
- [52: Frozen replay contexts, records and safe review access](052-replay-contracts.md); blocked by [35, 36, 37, 40].
- [53: Supervised capture and safe-refresh runtime lifecycle](053-capture-runtime-lifecycle.md); blocked by [35, 36, 37, 38, 40, 43, 51].
- [54: Sourced unit slot costs and team capacity](054-team-slot-capacity.md); blocked by [36, 39, 40, 41].
- [55: Complete Engine, Live, review-job and launcher runtime software](055-runtime-software-integration.md); blocked by [38, 42, 44, 53, 54, 56, 57].
- [56: Require positive fresh lobby completeness for roster-dependent valuation](056-lobby-completeness.md); blocked by [37, 40, 41].

- [57: Build-first Windows launcher and operator test handoff](057-windows-test-handoff.md); blocked by [53].

## Decisions so far

- 2026-10-13: Ticket 57 supplies the build-first launcher and [Windows operator handoff](../docs/agents/windows-test-handoff.md); six executable PowerShell workflow cases pass on macOS with package-manager stand-ins. Windows shell/native, current data and complete Live/runtime qualification remain pending.

- 2026-10-13: The owner plans Windows testing tonight and authorized commit/push. Ticket 57 extracts the independent build-first launcher and operator handoff from 55; full runtime, current data and device qualification remain open. Push verified work on `implement/mvp`, preserving unfinished worktrees and personal artifacts.

- 2026-10-13: [Ticket 54](054-team-slot-capacity.md) is closed after independent merge `f9e306f` of corrected exact `8ed6c80`. Root passed 464 Python tests (34.44 seconds, no skips, exit 0), 35 UI tests and required gates; actual public no-Live verification passed 145 cases. Independent review found and corrected discarded Baseline hex positions. Production preparation (48) resumes against sourced slot/capacity contracts; actual source values, capture producers and target latency remain unqualified.

- 2026-10-13: [Ticket 56](056-lobby-completeness.md) is closed after independent merge `85fd5e2` of exact candidate `4f3c782`. Root verification passed 420 Python tests (31.92 seconds, no skips, exit 0), 35 UI tests and required gates; independent public no-Live verification passed 103 cases. Full replay/review/harness (42) resumes. Capacity (54), Live surfaces (44), final runtime software (55), source/device qualification and historical native causality remain unfinished.

- 2026-10-12: Public Engine evaluation at `3a7bce2` produces identical unpaused placement scores for positive, false and unknown lobby-completeness certificates. Ticket 56 owns a shared full-roster guard before final runtime/candidate integration. Preserve independently qualified local and pairwise evidence; no smaller implied lobby or live verification claim is acceptable.

- 2026-10-12: Ticket 55 extracts final runtime software after 42/44/53/54. Ticket 45 retains the unresolved historical native qualification gate in 50 and remains open; no requirement is waived. Windows/device qualification in 49 depends on the actual software boundary 55, rather than an unrelated unresolved macOS cause. Production qualification remains 48. This preserves independent implementation and platform evidence without claiming the complete MVP is qualified.

- 2026-10-12: Supervised capture and safe-refresh lifecycle software (53) closed after different-merger integration `5fbdf5b` of corrected exact `4b32427`. Session recovery retains unfinished original logs and pins while safely releasing stopped writers; observed active LCU phases block publication even without initialized capture. Root verification passed 403 Python tests without skips in 31.73 seconds, process exit 0, plus 35 UI tests and required import/schema/lock/type/build gates. Full replay/review/harness (42) now proceeds from this integration; final Live/Engine dispatch and jobs remain in 45. Production, Windows/device and historical native-cause qualification remain open.

- 2026-10-12: Production preparation exposed the unit-count/team-slot mismatch. Ticket 54 implements generic sourced capacity consumption before final candidate/runtime qualification. Cached Riftbeast capacity differs from the dated prelaunch overview, so ticket 48 preserves the conflict rather than selecting an unsupported current constant. Its unfinished preparation worktree remains preserved while the same owner fixes 54 in a fresh worktree.

- 2026-10-12: Decision software (41) closed after different-merger integration `76eacf0` of corrected exact `cfc9c0b7`. All reproduced producer/model/render defects were fixed with public regressions. The merged root passed 358 Python tests in 26.76 seconds without skips, exit 0, plus 33 UI tests and import/schema/lock/type/build gates. Replay (42), Live surfaces (44) and production preparation (48) are now unblocked. Capture lifecycle (53) remains under independent recovery review. Current production data, Windows/device/resource qualification and the historical native cause remain explicit gates.

- 2026-10-11: Frozen replay contracts (52) closed after different-merger integration `b5c3d88` of exact `7cbb71d`. The root passed 308 Python tests in 18.99 seconds without skips, process exit 0; independent replay/storage checks and import/schema/lock gates passed. Causal prefixes, retrospective validity, immutable historical data, cache identity and locked review access are verified software boundaries. Full policy/cost/grouping/metrics/fitting/CLI work remains in 42, which still waits for 41; full-game resource use remains unqualified.

- 2026-10-11: Ticket 53 extracts capture/session/data lifecycle wiring from 45. Its software dependencies are closed, so it proceeds alongside 41 and 52. Final Live/Engine dispatch, review jobs, run workflows and complete runtime verification remain in 45; native cause 50 still gates final qualification.

- 2026-10-11: Source-provenance software ticket 51 closed after independent merge `91465f1` of exact `3e8a8de`. Root passed 281 Python tests in 14.61 s, no skips, process exit 0, plus both import contracts, schema and lock checks. Payload publication/identity remains distinct from donor hints; rejected attempts cannot relabel qualified last-good data. Production source/patch/cohort qualification stays in 48, and the historical native cause stays in 50.

- 2026-10-11: Ticket 52 extracts the frozen-log/context/cache/review-access prerequisite from 42. Its 35/36/37/40 dependencies are closed, so this software slice proceeds while 41 finishes. Full policy attribution, costs, review, evaluation and fitting remain in 42.

- 2026-10-11: Full capture software ticket 37 closed after independent merge `7963682` of corrected `9f0adb7`. Root checks passed 262 Python tests in 16.23 s without skips, process exit 0; both import contracts, schema and lock checks passed. Pinned equipped-item trait grants now project through `from_data`; unknown or invalid metadata still fails completeness. Production metadata/assets (48), Windows/recognition/device evidence (49), runtime lifecycle (45) and the historical native cause (50) remain open.

- 2026-10-11: Ticket 51 extracts the tested source-provenance prerequisite from 48. A donor endpoint's metadata must not qualify the augment-tier payload, and configured cohort goals must be checked against provider evidence. This software work can proceed before 41; production data qualification remains in 48.

- 2026-10-11: Ticket 40's Engine software boundary is closed after ownership merge `472bea4` and phase merge `27aeb7f`. Independent merged-root Engine checks passed 74 tests; the phase worktree passed 209 full-suite tests with process exit 0. The recorded inference timeout and historical native abort remain explicit. Native investigation/prevention stays open in ticket 50 as a parent/final-runtime gate; closing this domain does not declare complete integration or device qualification. Ticket 41 is now unblocked.

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
