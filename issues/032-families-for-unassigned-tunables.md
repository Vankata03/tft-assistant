---
id: 32
title: "Families for unassigned tunables"
labels: [wayfinder:grilling]
status: closed
assignee: claude-code
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

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. The owner set the fallback Lines for unguided comps and accepted the other recommendations.

Two gaps outside the ticket's list were settled with it: confidence had no scale, and the classifier's similarity had no normalization, so their thresholds had no unit.

- **Board power.** `item_values` is hand-set and sets only the shape of the item term: finished item 1.0, component 0.35, and 0.25 more per finished item on a unit of cost 3 or more. The fitted `item_weight` is the scale. Final boards rarely hold loose components, so the shape cannot be fitted.
- **Comp classifier.** Similarity is divided by the comp's own total weight, so it runs from 0 to 1. `classifier_weights` (carry ×3, key units ×2, others ×1, bench ×0.5) and `classifier_threshold` (0.5) are hand-set. Report only: the label at each stage against the label of the same player's final board.
- **Line candidates.** `gold_floors` (50, 30, 10, 0), `all_in_rounds_left` (2) and `stabilize_rounds_left` (3) are hand-set. They only decide which candidates exist. A new report-only **widened-candidate check** replays with floors every 10 gold, the two gates removed and the candidate caps raised (`line_candidate_cap`, `challengers_simulated`, `slam_candidate_cap`, `open_candidate_count`), and reports how often the chosen advice changes and by how much expected placement.
- **`default_lines_by_carry_cost`** is computed at each refresh: the most common Guide Line among Guides whose carry has that cost. Fallback for a cost no Guide covers (owner's values): the Line rolls at level 5, 6, 7, 8 or 9 for a 1- to 5-cost carry.
- **`augment_flag_prior_multiplier`** is family 3, starting at 2 (a flag raises shrinkage). It stays dormant until augment statistics return, then is set by holdout across patches.
- **Not tunables.** The bench priority order is a fixed rule, and bench size is game data, so `hold_priority` and `bench_budget` leave the tunables file. The threat keyword lists are per-set data in the static file, carried over each patch and rebuilt on the new-set repair checklist.
- **Game plan.** `open_candidate_count` (k = 3) is hand-set by the 100 ms budget and covered by the widened-candidate check. The commitment triggers are fixed rules except `commit_latest_round` (3-2), which is hand-set.
- **Sightings.** `sighting_full_weight_rounds` (start 2), `sighting_half_life_rounds` (start 1; the age weight halves each round after full weight ends) and `sighting_persistence_weight` (start 2, fading with the age weight) are family 1, fitted on consecutive sightings of the same opponent in game logs. New gate: they beat a model with no persistence on the log-loss of the next sighting.
- **`transition_tolerance`** is family 2, z = 1, from the fitted board-power error. Starting floor: 2 % of the stage's par board power.
- **Confidence.** A number from 0 to 1 in three bands. Low is below `confidence_medium_min` (0.5) and medium runs from 0.5 up to `confidence_high_min` (0.8). Surfaces drop advice below `confidence_show_min` (0.2). Low-confidence advice shows dashed and is never spoken; voice speaks medium and high. "Capped at medium" means below 0.8. All three are hand-set. Report only: prediction accuracy per band, which must improve from band to band.
- **`board_reader_identity_min`** (0.55, TFT-COACH's floor) is hand-set. Report only: on disagreements, which source the match API's final board proves right, per confidence bucket. Purchase-tracking auto-labels are not used, because they would bias it toward purchase tracking.
- **`field_max_age_seconds`** is per field and shared by every sub-engine, replacing a maximum age per sub-engine and field: 2 s by default, 0.5 s for the shop in roll-down mode. Hand-set. Report only: the stale-silence share per field.
- **Names.** Every prose-only tunable is named now, so the build has no naming decisions left.

Updated: `docs/spec/tunables.md` (no Unassigned rows left; new Computed group and "Not tunables" entries), `docs/spec/engine.md`, `docs/spec/sub-engines.md`, `docs/spec/capture.md`, `docs/spec/surfaces.md`, `docs/spec/patch-workflow.md`, `docs/spec/review-and-harness.md` (new "Checks on hand-set tunables" section and sighting gate) and the spec's open items. Glossary term Confidence added to `CONTEXT.md`.
