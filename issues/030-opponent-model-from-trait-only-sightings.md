---
id: 30
title: "Opponent model from trait-only sightings"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: []
---

## Question

How does the Engine model opponents when a sighting gives only the scouted player's traits?

"Benchmark open-source board recognition on probe frames" settled that scouted boards give traits only in v1: the board reader does not read opponent units, star levels, items or hexes. Every player's HP still comes from the HUD. Several earlier resolutions assume a sighting gives units and star levels:

- "Board and lobby strength heuristic" computes an opponent's board power from the sighting, imputing only what is missing (unseen items, empty slots below the opponent's level). With traits only, every unit is unseen.
- The same ticket's comp classifier labels opponents by unit overlap with each comp's final units. The contested count in "Transition and pivot domain model" uses those labels and the number of opponents holding 2 or more copies of a carry.
- "Econ, level and roll Line simulation" removes copies seen on opponents' boards from the pool for hit odds, and starts each simulated opponent from their last sighting.
- Win chance per opponent (second screen, and Baseline mode per "Board and lobby strength heuristic") is `win_probability` against the sighting's board power.

Decide, for each of these, what a trait-only sighting contributes: for example board power estimated from active trait breakpoints and the opponent's level, comp labels inferred from trait combinations, a contested term from traits, or a fallback to the growth curve with no contested term and no pool reduction. Decide what confidence each carries. The decision to read traits only in v1 stands; reopening opponent unit reading is out of this ticket.

Raised by "Assemble the MVP spec" as a gap between settled tickets. On resolution, update the spec's open items in `docs/spec.md` and the affected sections in `docs/spec/`.

## Comments

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. A background experiment measured how well a board's units can be recovered from its trait counts. Findings and scripts are on the throwaway branch `research/trait-vector-unit-inference` in `research/trait-vector-unit-inference.md` (commit `f7a8864`). It used 792 final boards from the owner's 99 latest Set 18 matches, with the champion and trait mapping from CommunityDragon.

**Measured facts**

- The scouted trait panel lists every trait on the board, active and inactive, with its unit count. The opponent's level is the number on their tactician's nameplate (probe frame at 2-2).
- With three Set 18 rules (Lux adds Avatar plus 2 in one origin, Elder Dragon adds 2 Riftbeast, Kha'Zix gains any subset of his evolution traits), 96.8 % of boards reproduce their trait vector exactly. The rest hold summons or augment-granted trait counts.
- Emblems known, full panel: the top-ranked unit set is exact on 95.0 % of boards, with 99.1 % per-unit precision and recall.
- Emblems unknown (up to 2 of slack): the top set is exact on 85.9 %, at 98.3 % precision and 94.7 % recall. That needs an emblem-count prior and a size-against-level prior; unit frequency alone gives 29.2 %.
- The panel shows at most 9 rows plus an "N+" button. In the probe game the hidden rows were inactive. 66 % of final boards have more than 9 traits. With 9 rows and emblems known, the top set is exact on 70.6 %, at about 94.5 % precision and recall. The combined case (unknown emblems and a cut panel) was not measured.
- Three pairs share their traits and can never be told apart: Ahri and Karma, Brambleback and Murkwolf, and Rengar and an unevolved Kha'Zix.
- Solve time is 0.1 to 1 ms median and about 46 ms worst case in pure Python.
- The probe game finished 1st, not just top 4.

**Decisions**

- **Sighting.** A sighting is the trait panel's visible rows with their unit counts, the hidden-row count and the opponent's level read from the nameplate. Level advances along the standard level calendar between sightings.
- **Inferred board.** A solver enumerates every set of distinct units whose trait counts reproduce the visible rows. Hidden rows count as inactive traits. Up to `emblem_slack_max` (2) counts may come from emblems; opponents' items stay unread. Set-specific trait rules live in the per-patch static file. Each candidate set is weighted by each unit's public play rate this patch, `emblem_count_prior`, `size_level_prior` and a persistence boost (`sighting_persistence_weight`) for units on the previous inferred board, fading with its age. The output is a probability per unit; downstream uses read these, never a single set. Trait-identical pairs split by the prior.
- **Board count and stars.** Opponents' boards are assumed full (units equal level); health bars are not counted. Star levels are never seen and come from `opponent_star_mix` by round and cost, fitted on the owner's own boards in game logs, with a hand default table until logs exist.
- **Board power** is an expected value: the exact trait term from the visible rows, plus Σ P(unit) × expected unit-star power under `opponent_star_mix`, plus filler slots at the level's average power, plus the stage-average item term. The same number feeds win chance, the Line simulator's opponent start, `placement` and the growth-curve correction. Boards are not sampled inside rollouts.
- **Pool reduction** removes P(unit) × the expected copies at the unit's cost under `opponent_star_mix`, fading after about 2 rounds. Benches are unseen, so contest is underestimated, never overstated.
- **Labels and comp-level contest.** An opponent's label is the classifier's expected similarity (weight × probability, no bench term) against the same threshold. The comp-level count becomes display and reason text only, with no channel into hit odds. The "2 or more copies of the carry" clause is dropped, because stars are never seen.
- **Confidence.** Each sighting has an inference certainty, the probability of its top candidate set. Advice that depends on opponent units carries the age weight times this certainty. Threat tags and the threat share carry the age weight only. The second screen shows the certainty beside each opponent's freshness bar.
- **Measurement.** A new harness metric compares the last inferred board of each opponent scouted in their last stage alive with their final board from the match API: per-unit precision and recall and the exact-set rate. The same data refits `emblem_count_prior` and `size_level_prior` between 10-game blocks.

**Spec updated:** `docs/spec/engine.md` (Contested, Comp classifier, new Opponent model section, error measurement), `docs/spec/capture.md` (scouted fields), `docs/spec/sub-engines.md` (hit odds, fights), `docs/spec/surfaces.md` (opponent table), `docs/spec/tunables.md` (new Opponent model table), `docs/spec/review-and-harness.md` (prediction list) and `docs/spec.md` (build steps 2 and 5, open items). Glossary: Sighting amended and Inferred board added in `CONTEXT.md`.

Input posted to "Baseline mode and opponent sightings" and "Families for unassigned tunables".
