---
id: 56
title: Require positive fresh lobby completeness for roster-dependent valuation
labels: [implementation:task, bug]
status: closed
assignee: codex-review-harness
parent: 34
blocked_by: [37, 40, 41]
---

# Require positive fresh lobby completeness for roster-dependent valuation

## Reproduction

At integration `3a7bce2`, use the declared synthetic `patch()` and `snapshot()` from `core/packages/engine/tests/test_planning.py`. Call public `evaluate(snapshot(lobby_complete=value, pinned_line={'id':'hold','levels':{},'rolls':{}}), GameHistory(), patch(), 'review')` for `value=True`, `False` and `None`.

Every case produces unpaused econ advice and the same six scored placements, `1.3708828427399904`. The capture boundary already supplies a separate lobby-completeness certificate. A partial or uncertified roster must not be treated as the full alive-opponent set for placement, Line valuation or next-opponent probabilities. The numbers are a software-fixture reproduction, not an owner-game estimate.

## Sources

- [Engine specification](../docs/spec/engine.md), [capture specification](../docs/spec/capture.md) and [approved public seams](../docs/agents/implementation.md).
- `tft_engine.lobby.alive_lobby`, strategic preparation/required-field fingerprints, domain dependencies and deterministic simulation seeds.
- Integrated capture (37), decision (41) and frozen replay (52) contracts; current Live display work (44) already identified the need to suppress partial-roster probabilities.

## Acceptance

- Require a fresh, sufficiently confident literal `lobby_complete=true` wherever valuation or probability needs the full alive roster. Missing, false, non-boolean, stale or insufficient-confidence certificates produce explicit unavailable/paused output, not a smaller implied lobby.
- Apply the guard at the shared responsible layer and preserve it through strategic preparation, actual Line/choice simulation, cache/seed and dependency fingerprints. A completeness change must not reuse a qualified full-roster result. Do not patch only the UI.
- Preserve independent local advice and valid observed pairwise fight metrics where their own required fields are qualified. Missing full-roster coverage must not invent other players or unnecessarily erase independently known outcome facts.
- Add public Engine red/green cases for the reproduced positive/false/missing cases and stale/type/conditional-choice behavior. Update declared positive fixtures with explicit certificates; do not weaken capture freshness, ownership, source or mode guards.
- Run appropriate Engine/replay/runtime/Baseline, import/schema/lock and relevant combined gates. Coordinate 42/44/54 consuming fixtures and requirements; merge current integration before exact committed handoff and use a different merger.

## Scope and qualification

This is a narrow software guard. Current production data and actual Windows capture remain 48/49; historical native causality remains 50. Do not access owner credentials, collect matches, start the measurement run or describe fixture outcomes as live evidence.


## Implementation evidence

### 2026-10-12 — Public guard and fixture correction

The initial reproduction expanded to literal false/missing/non-boolean coverage, stale and future timestamps, low certificate and roster confidence, and previously qualified history. The shared roster guard now rejects all these states, clears current fits and Lines, and runs before a simulation cache lookup. Required-field gates, original-state choice projection, next-opponent threat probabilities, replay seeds and advice dependency evidence use the same coverage contract. Qualified static tiers and sourced base own-board layouts remain available; observed pairwise models do not require full-roster coverage.

An actual CapturePipeline external-OCR fixture reads all eight rows, then seven rows 0.25 seconds later. The prior full lobby stays fresh with its original read timestamp, but the newer false certificate immediately prevents roster-dependent valuation. No rows or read timestamps are invented. Positive Engine/replay fixtures now declare their own coverage certificates.

The first combined run retained one failure: 148 passed and one existing high-HP one-round-buff `gain > 0` assertion failed after the required semantic seed change. On tape `1893440055913326485`, only surviving rollout 20 differed: placement moved from 2.871278864944699 to 2.878425915098738, with mean paired gain -0.00005583632932842919. Holding the tape and changing only `terminal_gold_weight` from 0.001 to zero changes the gain to +0.000006663670671570865. The terminal subtraction implies surviving held gold of 128 before versus 120 after; the immediate win breaks a loss streak and changes later income. A buff therefore need not improve placement. The revised declared five-HP fixture checks its current-round survival effect, expiry on the next round and identical paired seeds, rather than asserting a universally positive economy-adjusted gain. This is synthetic software evidence, not a current-game rule or owner result.

### 2026-10-13 — Final verification

The final unchanged implementation passed all 420 Python tests with the train group and cached pinned models, no skips, in 31.27 seconds; the process exited zero with two existing Torch ONNX-export deprecation warnings. The earlier 420-test run also exited zero in 40.64 seconds. The last cleanup run started before the usage interruption could not be retrieved (`Unknown process id 81758`), so its result is unknown; the final run records both output and process exit under the ignored worktree proof directory.

Additional checks: Engine 127 tests passed in 7.61 seconds; the final positioning/guard slice passed 53 in 5.11 seconds; the installed public environment without Live passed 95 guard/replay/runtime/Baseline cases in 9.99 seconds. One initial public selector incorrectly included the unconditional owner-build `tft_live` import smoke: 102 passed and that import failed as expected because Live was removed. The corrected public workflow selection passed without changing or skipping tests. Live and train were restored afterward. UI 35 tests, typecheck, generated-type check and build passed. Both import contracts, schema check, frozen lock check, scoped F821 and diff checks exited zero. The bounded documentation preservation check retained all 213 constraints.

The branch includes integration `be571ca699fbe9d2664fb2955f6080c5073f6267`; exact commit and independent integration are reported at handoff. Ticket closure remains with the parent after a different merger reviews it. Production source qualification, Windows capture and historical native causality remain tickets 48, 49 and 50. No owner API, match collection or measurement run was used.

## Resolution — 2026-10-13

Exact candidate `4f3c7827f2dec1487be2ce505001ce2c848d9d2c` was reviewed and independently integrated as `85fd5e2a678fcbfe748861bfcabdecb39b9c1806`. The merger reproduced qualified True output (18 Lines, two fits, unpaused) and explicit False/None output (zero Lines and fits, paused). The integrated root passed 420 Python tests without skips in 31.92 seconds, exit 0, with two existing Torch ONNX warnings; UI passed 35 tests plus type, generated-type and build checks. Import, schema, frozen synchronization/lock and diff checks passed. A separate installed public environment with Live physically absent passed 103 cases in 10.30 seconds; Live and train were restored afterward. The initial merger selector named nonexistent `test_baseline.py` and exited 4 without running tests; the corrected focused selection passed 146 cases in 12.52 seconds. These failed/unknown attempts remain recorded above and are not counted as successful gates.

The software acceptance is fulfilled. Ticket 42 resumes from this integration; production sources, Windows/live-game qualification and historical native causality remain open in 48, 49 and 50. No owner API or measurement run was used.
