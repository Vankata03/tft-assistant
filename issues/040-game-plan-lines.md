---
id: 40
title: Game plan, transitions and seeded Line simulation
labels: [implementation:task]
status: open
assignee: implement/ticket-40
parent: 34
blocked_by: [39]
---

# Game plan, transitions and seeded Line simulation

## Sources

- [docs/spec/engine.md](../docs/spec/engine.md)
- [docs/spec/sub-engines.md](../docs/spec/sub-engines.md)
- [docs/spec/tunables.md](../docs/spec/tunables.md)

## Acceptance

Deterministic pure advice, history-folded plan and hysteresis, comp fit screening/simulation, commitment/pivots/divergence/lock, strongest-owned-board transition, common-random-number Monte Carlo Lines, closed-form shop odds, floors/horizon/death/econ/streak, projections and pinning.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

### 2026-10-10 — Software implementation and verification

- Implemented pure advice/evaluation, history-folded plans, screened/simulated comp fit, commitment, Backup-aware roll sales, pivots, locks/divergence, line hysteresis/pins, transition Swap/Hold/Sell and shared decision hooks. API: `docs/agents/engine-contracts.md`.
- Line simulation batches concrete Line × rollout states in NumPy and caches identical copy/level board states. Greedy-plus-swap refinement and deadline membership order now agree with public transition projections in trait-breakpoint and retained-item regression examples. Addressed common random numbers preserve combat, death, streak, shop and effect-pair variance. Public batched-versus-individual Line results match exactly; zero-effect pairs have zero gain/error.
- Retained initial unbatched 65-Guide timing: 1.84751079097623 s. Batching/memoization was checked against complete Advice/LineResult JSON before subsequent behavioral corrections. Later growth-table reuse also preserved byte-identical full JSON. Those optimization comparisons do not claim parity between corrected behaviors and the original implementation.
- Mac15,10, Apple M3 Max, 14 logical CPUs; 65 synthetic independent unit types, 65 Guides, 3 simulated comps × 12 floor-expanded Lines = 36 scored concrete Lines, 64 rollouts per Line, plus 3 reason counterfactual Lines. The family cap preserves all configured floors; concrete count exceeds the family count. Actual simulation-pass counters include any Backup reconciliation.
- After swap/deadline corrections, five combat runs: 0.301558, 0.277688, 0.360604, 0.287018, 0.474923 s (median 0.301558 s). Five PvE runs: 0.354417, 0.351528, 0.343273, 0.433240, 0.286245 s (median 0.351528 s). These are bounded Mac smoke timings with synthetic statistics, not a controlled target-device benchmark. The 100 ms budget is unmet here and remains ticket 49.
- Cached primary CDragon roster smoke: 65 independent unit types, 9 Lux forms, Avatar 1/chosen origin 2 grants; visible Avatar/Blackthorn rows plus 2 hidden traits produce exactly 44 candidate unit sets, certainty 0.026068821689259645. Latest measured inference took 0.011671 s with state cap 10000 and no fallback. These priors remain synthetic; current production source/Guide readiness remains ticket 48. The explicit cap fallback is covered separately and retains no partial posterior.
- Reproduce from the repository root: `uv run --project core python core/packages/engine/tests/benchmark_engine.py --repeats 5 --combat --roster-cache ../references/cdragon/latest-en_us.json --result-json /tmp/tft40-combat.json`; omit `--combat` for PvE and omit `--roster-cache` if the separate reference cache is unavailable. `--result-json` writes every Advice and LineResult for deterministic comparison. Source-cache path assumes the ticket worktree layout.
- Profile with `uv run --project core python -m cProfile -o /tmp/tft40.prof core/packages/engine/tests/benchmark_engine.py --combat`. Remaining costs are the shop/pool loop, NumPy cumulative sums and cached board selection. A compiled loop or further measured optimization may still be required by ticket 49; reducing rollout variance or silently dropping floor candidates is not an acceptable budget fix.
- Before swap refinement, integration checks passed: 171 Python tests, 7 skips for optional training/ONNX/model-cache requirements; Engine 49 tests, both import contracts, and `uv lock --check`. After refinement and explicit generic-item regression, Engine 53 tests pass. Final integration verification is recorded in the follow-up comment below.
- `terminal_gold_weight` is an explicit family-1 terminal buying-capacity approximation for surviving states only. Death rank reuses placement coefficients against captured opponent HP/projected power and freezes at death; opponent eliminations are not simulated. Initial/default coefficients remain unqualified until harness fitting. Reason-only key arrival is a free-copy counterfactual at the roll-down deadline and never selects or prices an action.
- The fixed generic item state follows the 2026-10-04 amendments in ticket 18 and current sub-engines terminal/input clauses. It supersedes the earlier item-exclusion wording. The current-board transition counts selected equipment without transferring it; the rollout's initial generic item/high-cost-holder term stays fixed across subsets. Explicit item-state counterfactuals change that term with identical random draws. This is a deliberate model approximation, not a simulated physical handover.
- No Windows capture execution, held-out owner recognition accuracy, ranked live games, fitted owner-match parameters or Ryzen/game-running latency qualification is claimed. Status remains open for integration acceptance review; parent ticket 34 and qualification ticket 49 remain unfinished.

### 2026-10-10 — Final integration checks

Merged integration through `247f9ef` (capture promotion guard corrections and reader software closure) into ticket 40 at `41d9641`. Engine: 53 tests passed. Default core environment: 175 passed, 13 optional capture/training/model skips. With the explicit train group and cached pinned reader assets: `TFT_READER_TEST_MODELS=/path/to/cached/models uv run --group train pytest -q` passed all 188 tests in 18.48 s with two existing PyTorch ONNX-export deprecation warnings. The cached assets are external inputs, not owner-labeled accuracy evidence. `uv run lint-imports` kept both import contracts; `uv lock --check` and `git diff --check` passed. Bounded Engine-contract editorial preservation kept all 148 extracted facts/references without warnings. No target-device or live-game qualification was performed.
