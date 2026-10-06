---
id: 39
title: Board power, classification and trait-only opponent inference
labels: [implementation:task]
status: open
assignee: implement/ticket-39
parent: 34
blocked_by: [46]
---

# Board power, classification and trait-only opponent inference

## Sources

- [docs/spec/engine.md](../docs/spec/engine.md)
- [docs/spec/tunables.md](../docs/spec/tunables.md)

## Acceptance

Typed Engine snapshot/history/board/advice contracts, strength/win_probability/placement/surviving_units, shrinkage and item/trait terms, growth curve, classifier, exact trait constraints with emblem/hidden-row rules and priors, marginal opponent power and fading sightings.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

### 2026-10-06 — implement/ticket-39

Implemented immutable JSON-compatible snapshot, history, board and structured advice contracts; absolute unit/trait/item power; combat projections; growth calculation and corrections; normalized comp classification; exact trait-only posterior inference with hidden inactive rows, emblem slack, set-specific grants, size/play-rate/persistence priors and fading expected pool copies. The Baseline allowlist exposes only own-board strength, win probability and par growth lookup. Interface shapes are recorded in `docs/agents/engine-contracts.md`.

Unit top-4 rates shrink toward the cost-star binomial prior before the logit. Trait rows use the separately named family-3 `trait_prior_strength`, centered on the lobby rate. This explicitly handles valid thin 0% and 100% statistics without a fabricated epsilon or an average-placement proxy. Missing required data raises an actionable `DataError`; missing unit splits use a flagged, lower-confidence cost-star prior.

Verification on macOS: 19 Engine public-boundary tests passed, including worked endpoint and combat examples, JSON round trips, exact hidden/emblem/special-rule constraints, persistence and growth. The exact ambiguous-set test verifies 215,553,195 candidates and marginal probability 8/45 within a one-second subprocess bound. Both import-linter contracts are kept. Windows capture and live-game checks remain separate. Actual roster performance, fitted owner-match parameters and the 100 ms Ryzen target remain unqualified; this implementation does not claim those external results. The complete advice pipeline belongs to ticket 40.
