---
id: 54
title: Model sourced unit slot costs and team capacity
labels: [implementation:task, bug:engine]
status: closed
assignee: codex-capacity-engine
parent: 34
blocked_by: [36, 39, 40, 41]
---

# Model sourced unit slot costs and team capacity

Production preparation exposed a concrete representation gap: the current board-power guard and strongest-owned selector compare `len(board.units)` with level. A two-slot unit can therefore be recommended without reserving its second slot, while extra team capacity cannot be represented consistently. This software correction is separate from qualifying the actual patch values in ticket 48.

## Sources and evidence

- [Engine specification](../docs/spec/engine.md), [decision engines](../docs/spec/sub-engines.md), [trait inference](030-opponent-model-from-trait-only-sightings.md), and final [decision contract](../docs/agents/decision-contracts.md).
- Checked October 10 CommunityDragon payload at ignored `worktrees/references/cdragon/latest-en_us-2026-10-10.json`, SHA-256 `17d19792f662cec404aa071492ae9144a2d2677d2eeb1e0d7d8db9b52a47a9c7`.
- Its `DA_18_ApexPredator` description explicitly states Elder Dragon takes two slots and grants two Riftbeast. Playable `DA_18_ElderDragon` carries that trait. The cached `DA_Riftbeast18` effect at `minUnits=10` has `TeamSize=2.0`.
- Riot's [July 27 prelaunch overview](https://teamfighttactics.leagueoflegends.com/en-sg/news/game-updates/enchanted-wilds-overview/) says Elder Dragon occupies two slots/contributes two Riftbeast, but lists the maximum-team-size bonus as one and warns values may change. Preserve that dated conflict; neither value becomes a hardcoded current rule.

## Acceptance

- Define one deep, source-aware capacity boundary distinguishing physical unit count, occupied team slots, hex positions and maximum team-slot budget. Represent explicit per-unit slot costs and supported capacity modifiers, including trait breakpoints and positively captured capacity where available. Document how ordinary-unit rules are sourced. No untagged one-slot fallback may silently qualify an unknown unit.
- Validate finite integral costs and modifier shapes, reject booleans and invalid/conflicting metadata, and preserve unavailable status when required capacity evidence is missing. Keep canonical/shared-pool identities and trait-grant multiplicities consistent; Elder Dragon's Riftbeast contribution is two in total, not an extra two on top of one.
- Apply the boundary consistently to own-board power/validation, strongest-owned and forced-Guide selection, transitions, Line simulation, physical unit grants/polymorph/choices, and trait-only opponent inference where team-size constraints enter. Keep distinct observed unit-count and slot-budget evidence separate; do not manufacture opponent units or extra capacity.
- Preserve legality when a larger unit needs room, when capacity appears/disappears with a proposed trait/item state, and when owned units have duplicate identities. Do not score an illegal board as a valid stronger alternative. Any unsupported capacity activation/transition rule must pause the dependent valuation rather than infer an executable sequence.
- Verify through approved public Engine/data boundaries: two-slot selection versus ordinary units, legal and over-budget boards, explicit breakpoint bonuses, malformed/missing metadata, forced-Guide limits, same-seed Line/choice valuation and applicable inference constraints. Use source-tagged fixtures with declared rules; tests are not current patch or device qualification.
- Preserve other planning/ownership/freshness/phase gates and paired evidence. Merge current integration before a clean exact handoff and obtain a different merger agent. Reconcile the final consumer shapes with ticket 48's isolated preparation before any production candidate claim.

## Public reproduction

At integration `b7db707`, a bounded call through actual `CommunityDragon.entities()` and public `estimate_strength()` accepted a board containing only `DA_18_ElderDragon` at level 1. The checked unit and trait identity/text were retained from the cached primary payload; power/statistical inputs came from the explicitly synthetic `test_planning.patch()` fixture, with neutral tagged trait priors. The call returned power 5.0 rather than rejecting a two-slot unit under a one-slot budget. This reproduces the capacity defect through the public software boundary; the power number is a fixture result, not a qualified current-game estimate.

## Qualification boundary

This implements consuming sourced rules. Ticket 48 still qualifies real slot costs, capacity bonuses, grants and other patch mechanics. Ticket 49 retains Windows capture and target-device evidence. No owner API, game, run, fit or production data publication is authorized by these software fixtures.

## Implementation evidence — 2026-10-13

- Candidate branch: `implement/ticket-54`, based on integration `1926089d5d58d44b84cf13a426cbcaf8aaf3decc`, including the independently merged ticket 56 lobby certificate. This record requests different-agent review; the issue remains open until integration acceptance.
- Contract: [capacity-contracts.md](../docs/agents/capacity-contracts.md). Shared Data validation supplies explicit slot costs, level budgets, continuous trait modifiers, held augments, three distinct equipment/inventory scopes and an explicit conservative transition policy. Own power, Guide selection, transitions, Lines, grants and applicable inference consume that boundary. Transition advice retains indexed intermediate slot/bench proofs. No unknown unit gets an implicit one-slot rule.
- Public regressions cover ordinary versus two-slot selection, trait-supported legal boards, stale/conflicting budgets, malformed metadata, duplicate physical units, bench positions, forced Guide limits, exhausted transition search, grants/polymorph overflow, equipment sale/rebuy, same-seed choice valuation and slot-aware inference. The final capacity slice has 38 passing examples. The narrow direct `simulate_lines` regression failed before the pre-Guide ownership guard: a Guide form had incorrectly certified an owned variable base. It now rejects that base and accepts positively typed ownership. Six malformed breakpoint/boolean observed-count regressions also failed before strict validation and then passed.
- Capture's public two-slot example uses a declared reviewed counter semantic and tagged slot certificates: one physical unit occupies two slots under budget two. Unknown semantics or missing certificates cannot certify complete ownership. Baseline's own-board protocol and indirect-import allowlist remain covered. The new-set CLI retains both the uncertified no-publication/no-calendar/no-archive failure and the positive declared-certificate carry/archive workflow; the narrow overlay changes existing canonical metadata only.
- Final core command, from `core/`: `TFT_READER_TEST_MODELS=/Users/vankata/Desktop/Projects/tft-assistant/worktrees/references/tft-coach/assets/models uv run --group train pytest -q --tb=short`: **461 passed, no skips, 32.85 seconds, exit 0**. Two existing Torch ONNX export deprecation warnings remain. The preceding full runs were 453, 459 and 460 passes as final public cases were added; they do not replace the final 461-case result.
- Gates: `uv run --group train tft-schemas --check`, `uv lock --check`, `uv run --group train lint-imports` (two contracts kept), and the scoped `uv tool run ruff check --select F821 packages/engine/src packages/data/src packages/capture/src src/tft_core/baseline` all exited 0. UI `npm test` passed 35 tests; `npm run check:types`, `npm run typecheck` and `npm run build` exited 0. Dependency symlinks were removed from the worktree. The bounded capacity reference editorial pass preserved all 58 extracted constraints; an older draft comparison's three cross-backtick spans were invalidated by intervening API additions, not prose deletion.

### Reproducible bounded CPU smoke

From `core/`, run `uv run --group train python packages/engine/tests/benchmark_engine.py --combat --repeats 3 --result-json /tmp/tft-assistant-54-final-batched.json`. Repeat with `--no-reuse --result-json /tmp/tft-assistant-54-final-uncached.json`; compare the complete bytes, not averaged outcomes. Add `--large-unit` for the declared two-slot fixture. Add `--roster-cache worktrees/references/cdragon/latest-en_us-2026-10-10.json` using its absolute root path for the checked identity/grant namespace inference smoke.

- Host: Mac15,10, Apple M3 Max, 14 logical CPUs. Synthetic workload: 65 roster identities and 65 Guides; three comps × 12 concrete Lines = 36 scored Lines, all configured floors retained, 64 rollouts each. Three reason counterfactual Lines give 39 executed Lines and 2,496 executed rollouts. Family cap seven still means schedule families, not seven floor-expanded Lines.
- Ordinary-unit cached timings: 0.328891, 0.320186 and 0.315380 seconds. Uncached: 0.328673, 0.313839 and 0.316212 seconds. Complete Advice/LineResult JSON is byte-identical: 159,853 bytes, SHA-256 `d411433b943bccfee5fca3eb0ce2682d2150748b1fdb40bd6d7456e2024e4020`. Individual shop/fight/death distributions and paired evidence remain in that output; the smoke did not replace variance with averages.
- Declared two-slot roster timings: 0.933969, 0.951256 and 0.952826 seconds. The generic-capacity path retains the public greedy/swap policy and physical equipment state rather than pricing an illegal board.
- Checked cached namespace inference: 65 base units, nine forms, explicit synthetic capacity/prior certificates and Lux/Elder grant declarations; 44 candidates in 0.004365 seconds, certainty 0.026069, no state-cap fallback. This bounds software runtime for those smoke inputs; it does not qualify live statistics, a production posterior or real slot rules.
- Both evaluation workloads exceed 100 ms. Target Ryzen/game-running qualification, Windows HUD evidence and the existing full-choice transport/resource budget remain unmet in ticket 49. Actual patch certificates and atomic transition semantics stay in ticket 48. Capture does not yet resolve variable base ownership to typed active forms or publish scoped remote budgets; these missing producers are explicitly retained in tickets 48/49. Dependent rollouts pause and remote inference uses visibly qualified par fallback. No production candidate was installed.

### Independent review correction — 2026-10-13

- The different merger reviewed exact candidate `9749a009edd0198285ad94cb1de2d25bf7d20028` and reproduced a Baseline projection defect: deployed positions `[0,0]` and `[28,1]` were discarded while constructing `OwnUnit`, so malformed boards received an unpaused par probability of 0.8807970779778823. Direct allowlisted power already rejected those hexes. The author-side public controller regression reproduced both failures before the correction; valid `[0,1]` passed.
- Baseline now preserves each supplied deployed position and bench inventory position through its own protocol. The capacity boundary validates deployed hexes; a bench slot numbered zero does not become a duplicate deployed hex zero. The three public examples now pass, including positively complete equipped-anywhere capacity inventory.
- Corrected focused Baseline/capacity slice: **54 passed, exit 0**. Corrected full train with the same model-path command above: **464 passed, no skips, 33.74 seconds, exit 0**, with the same two ONNX deprecation warnings. Import contracts (two kept), schemas, lock, scoped F821 and diff checks all exited 0. No UI/schema contract changed; the recorded 35 UI tests and type/build gates remain applicable. Engine benchmark code and outcomes did not change.
- Integration `1926089` remains an ancestor. Candidate 9749a00 and its initial failure evidence remain in history; this follow-up requests a new exact different-merger acceptance. Ticket 48 remains paused and its edits are preserved.

## Resolution — 2026-10-13

Corrected exact candidate `8ed6c80c98eaae0a9227caf1f3e8bf573b6c745d` was independently accepted and integrated as `f9e306fdb07bd292c6db60fb998dffebfe7bf2b0`. The independent public branch slice passed 118 tests in 3.83 seconds. Merged-root verification passed 464 Python tests without skips in 34.44 seconds, process exit 0, with two existing Torch ONNX-export warnings; UI passed 35 tests plus typecheck, generated-type parity and build. Both import contracts, schemas, frozen lock, scoped F821 and diff checks passed. With Live physically absent, 145 public capacity/lobby/Baseline/capture/replay cases passed in 8.37 seconds; default Live and train were restored, and the root was clean. An initial selector named nonexistent test files and exited 4 without running tests; the corrected discovery and passing runs are distinct from that attempt.

The sourced capacity software acceptance is fulfilled, including the independently reproduced Baseline projection correction. Ticket 48 resumes preparation against the final contracts. Current patch values, HUD semantics, unresolved active-form/remote-budget producers, Windows/game-running performance and historical native causality remain separate qualification conditions. Mac workloads remain above 100 ms; no owner workflow or production candidate was run or installed.
