---
id: 32
title: "Families for unassigned tunables"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

Which tunable family does each tunable that "Evaluation harness" did not classify belong to, and how is each first set?

"Evaluation harness" split tunables into three families (fitted on game logs, margins set from noise, priors from public statistics) plus a hand-set, report-only group. These tunables, settled elsewhere, appear in none of them:

- From "Econ, level and roll Line simulation": `gold_floors`, `all_in_rounds_left`, `stabilize_rounds_left`, `default_lines_by_carry_cost`.
- From "Board and lobby strength heuristic": `item_values`, `classifier_weights`, `classifier_threshold`.
- From "Augment decisions": `augment_flag_prior_multiplier`.
- From "Positioning decisions": the threat keyword lists.
- From "Shop, Wisp and carousel decisions": `hold_priority`, `bench_budget`.
- From "Transition and pivot domain model", named only in prose: the number k of Open candidate comps, the commitment triggers, the rounds a sighting keeps full weight (about 2), and the transition strength tolerance.
- From "Advice engine architecture" and "Game-state capture route": the confidence threshold below which surfaces drop advice, voice's stricter threshold, the vision confidence threshold above which the board reader's unit identity wins over purchase tracking, and each sub-engine's maximum field age.

For each, decide its family, its starting value or how the starting value is found, and whether the evaluation harness reports on it. Also decide whether the prose-only tunables get names in the tunables file now or at build time.

Raised by "Assemble the MVP spec" while compiling the tunables index. On resolution, update `docs/spec/tunables.md` and the spec's open items.

## Comments

### 2026-10-04 — claude-code

Input from "Opponent model from trait-only sightings": one more unassigned tunable, `sighting_persistence_weight` and its fade (the prior boost for units on an opponent's previous inferred board). It is listed in the Opponent model table of `docs/spec/tunables.md`. The other new tunables there have families: `opponent_star_mix`, `emblem_count_prior` and `size_level_prior` are fitted (family 1), and `emblem_slack_max` is hand-set.
