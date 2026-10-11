---
id: 41
title: Shop, Wisp, item, augment, carousel and positioning advice
labels: [implementation:task]
status: open
assignee: codex-decision-engines
parent: 34
blocked_by: [40]
---

# Shop, Wisp, item, augment, carousel and positioning advice

## Sources

- [docs/spec/sub-engines.md](../docs/spec/sub-engines.md)
- [docs/spec/tunables.md](../docs/spec/tunables.md)

## Acceptance

All remaining decision engines, required-field silence and confidence lowering, shared fit and same-seed valuation, bench priorities, item assignments/slams/handover/tools, augment fallback tiers/statistics/rerolls, Wisp effects, carousel choices, layout assignment and threat hysteresis.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

### 2026-10-12 — implementation candidate and verification

The decision registry now implements shop and bench priorities, exact current item assignment and component search, slam/hold pairs, physical board/bench equipment handovers and tools, stage-aware augment tiers/statistics/rerolls, sourced Set 18 Wisp effects and grants, carousel reranking, and exact positioning with causal threat hysteresis. Choice projections preserve immutable inputs, the original random tape, observed phase/ownership gates, every scored option and explicit baselines. Unknown models remain unavailable. `Statistic.pick_stage` is validated, persisted and included in refresh prior keys; patch validation accepts the implemented conditional and sale-modifier effects. The source/capture/paired-error/fingerprint/transport contract is [decision-contracts.md](../docs/agents/decision-contracts.md). Independent integration review remains pending; this ticket stays open.

The initial full train run before Baseline compatibility passed 351 tests in 22.90 seconds, exit 0. The final run after the additive stage/label adapter passed 352 tests in 23.15 seconds, exit 0, with two existing Torch ONNX deprecation warnings. Command, from `core`: `TFT_READER_TEST_MODELS=/Users/vankata/Desktop/Projects/tft-assistant/worktrees/references/tft-coach/assets/models /Users/vankata/Desktop/Projects/tft-assistant/worktrees/tooling/bin/uv run --group train pytest -q`. Public Baseline output and rendered cockpit/overlay regressions cover current-stage labels, unavailable rows and silent suppression; the generated schema and TypeScript types are synchronized. UI tests passed 32 tests; `check:types`, `typecheck` and `build` exited 0. Import contracts kept both boundaries, including the strict Engine allowlist. Schema/lock checks, scoped Ruff F821 and `git diff --check` exited 0. Unslop found no confirmed prose defects; the bounded consumer document preservation check passed. The checked code base included `d38ce89`; the later docs-only integration tip `a69ce98` was merged before the final handoff, with no consumer code change.

Bounded Mac CPU evidence uses Mac15,10, Apple M3 Max, 14 logical CPUs, with synthetic tagged data. `core/packages/engine/tests/benchmark_engine.py --combat --augment-pool 21 --rollouts 64 --repeats 2 --result-json /tmp/tft-41-final-cached.json` retained 65 unit types/Guides, three projected comps, 36 concrete candidate Lines plus three reason Lines, and 64 rollouts per Line. Cached evaluations took 1.171804 and 1.179692 seconds; `--no-reuse --repeats 1` took 6.314051 seconds. Request-local reuse reported 126 hits in 132 requests, six executed calls and 2,496 rollout-Line states. Every Advice and Line JSON record was byte-identical across the pair: 17,741,188 bytes, SHA-256 `4ac39cd6bbc4c4dfd0dc3c5395f1a4169e2073501b336172773a24473562bf67`. No candidate, conditional outcome or variance was removed. The ordinary 65-Guide combat workload took 0.267644 and 0.256443 seconds. A separate current cached CDragon roster smoke retained 65 independent types and nine Lux forms; trait inference took 0.004275 seconds with symbolic cap 10,000 and no fallback. These are Mac smoke timings, not target-device qualification.

The 100 ms Ryzen/game-running budget remains unmet under ticket 49. The full 17.7 MB evidence payload also needs bounded summary/reference transport and resource qualification in 44/45/49; content-addressed choice bundles now provide resolvable evidence IDs without discarding distributions. Ticket 48 must provide qualified patch effects, component/class/reference statistics, conditional Wisp prices, standard states and the recent-opponent policy. A stage-only offline reference cost does not model conditional free-price or round-gold eligibility rules. Ticket 53 owns the real gap-aware fight-history certificate producer; this consumer never fabricates that certificate. Windows capture accuracy, live games, fitted owner parameters and the remaining runtime/native gates are not established by these tests.
