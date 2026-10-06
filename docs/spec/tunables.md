# Tunables index

Part of the [MVP spec](../spec.md). Every number and threshold the Engine uses lives in the per-patch tunables file `data/<patch>/` (TOML), which the owner override file can change ([Advice engine architecture](../../issues/011-advice-engine-architecture.md)). Families come from [Evaluation harness](../../issues/027-evaluation-harness.md):

- **1, fitted** on game logs by maximum likelihood and gated.
- **2, margin**, set from noise: z times the standard error of the difference it guards, z = 2 for costly or sticky calls and 1 for cheap or reversible ones.
- **3, prior**, set from public statistics by empirical Bayes or holdout.
- **Hand-set**, report only, because no v1 data can set it. The harness checks each one with a report-only metric ([review-and-harness.md](review-and-harness.md#checks-on-hand-set-tunables)).
- **Computed** from data at each refresh, not tuned.

Every tunable has a name. [Families for unassigned tunables](../../issues/032-families-for-unassigned-tunables.md) named the ones earlier tickets described only in prose, and gave a family to every tunable that had none.

Static-file values (XP, gold, streak, interest and damage tables, shop odds, pool sizes, rules flags, Wisp effects, econ augment tags, tier pools, opening encounters) are game data, not tunables; see [patch-workflow.md](patch-workflow.md#static-file).

## Game plan, transition and pivot

Owner: [Transition and pivot domain model](../../issues/012-transition-and-pivot-model.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| Pivot margin per stage | 2 (z = 2) | Starting floors about 0.5 placement at stage 3 and 0.8 after the main roll-down |
| Pivot re-raise extra | 2 | Added to the pivot margin before a reverted pivot call returns |
| `open_candidate_count` | Hand-set | k = 3, the Open plan's candidate comps; set by the 100 ms budget |
| `commit_latest_round` | Hand-set | 3-2. The other commitment triggers are fixed rules ([engine.md](engine.md#state)) |
| `transition_tolerance` | 2 (z = 1) | Ties within it are broken by progress toward the target comp. Starting floor: 2 % of the stage's par board power |

## Econ, level and roll Line simulation

Owner: [Econ, level and roll Line simulation](../../issues/018-econ-level-roll-line-simulation.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `line_margin` | 2 (z = 1) | Starting floor about 0.1 placement |
| `terminal_hp_weight` | 1 | `b` in `placement()` |
| `opponent_growth_curve` | Computed; correction is 1 | Computed from statistics at each refresh; corrected against sightings |
| `rollouts_full` | Hand-set | Set by the 100 ms budget |
| `rollouts_reroll` | Hand-set | Set by the 100 ms budget; also used for gold-price pairs |
| `line_candidate_cap` | Hand-set | About 7 |
| `challengers_simulated` | Hand-set | About 2 |
| `gold_floors` | Hand-set | 50, 30, 10, 0 |
| `all_in_rounds_left` | Hand-set | 2; below it, floor 0 is always a candidate |
| `stabilize_rounds_left` | Hand-set | 3; below it, the stabilize Line joins the candidates |
| `default_lines_by_carry_cost` | Computed | Lines for unguided comps: at each refresh, the most common Guide Line among Guides whose carry has that cost. Fallback for a cost no Guide covers: the Line rolls at level 5, 6, 7, 8 or 9 for a 1- to 5-cost carry |

## Board power and lobby strength

Owner: [Board and lobby strength heuristic](../../issues/019-board-and-lobby-strength-heuristic.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `unit_weight`, `trait_weight`, `item_weight` | 1 | Fitted on the owner's final boards, then on game logs |
| Fight scale | 1 | Initial k in `win_probability` |
| `win_scale_by_stage` | 1 | Per-stage k, split from the pooled value past about 150 fights at a stage |
| `survivor_scale_by_stage` | 1 | c in `surviving_units` |
| `cost_star_baseline` | 3 | Fallback unit-star power for thin samples |
| `unit_prior_strength` | 3 | Binomial prior sample size for unit-star power; shrink the observed top-4 rate toward the cost-star prior before applying the logit |
| `trait_prior_strength` | 3 | Binomial prior sample size for trait-breakpoint power, centered on the lobby top-4 rate; fit separately from the unit prior |
| `item_values` | Hand-set | Shape of the item term only: finished item 1.0, component 0.35, and 0.25 more per finished item on a unit of cost 3 or more. `item_weight` is the fitted scale |
| `classifier_weights` | Hand-set | Carry ×3, key units ×2, others ×1, bench at half weight |
| `classifier_threshold` | Hand-set | 0.5 on normalized similarity; below it the label is "no comp" |

## Opponent model

Owner: [Opponent model from trait-only sightings](../../issues/030-opponent-model-from-trait-only-sightings.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `opponent_star_mix` | 1 | Share of 1-, 2- and 3-star units by round and unit cost, fitted on the owner's own boards in game logs; a hand default table until logs exist |
| `emblem_count_prior` | 1 | Fitted on match final boards, then on game logs |
| `size_level_prior` | 1 | Distinct units against level; fitted like `emblem_count_prior` |
| `emblem_slack_max` | Hand-set | 2; trait counts the solver may assign to emblems |
| `sighting_persistence_weight` | 1 | Prior boost for units on the opponent's previous inferred board; start 2 (the prior is doubled). Fades with the sighting's age weight |
| `sighting_full_weight_rounds` | 1 | Rounds a sighting keeps full age weight; start 2 |
| `sighting_half_life_rounds` | 1 | After full weight ends, the age weight halves every this many rounds; start 1 |

## Items

Owner: [Item decisions](../../issues/020-item-decisions.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `item_class_prior` | 3 | AD, AP, tank, utility |
| `item_prior_strength` | 3 | |
| `component_income_by_stage` | Hand-set | |
| `component_discount_by_stage` | Hand-set | Falls to about 0 by stage 5 |
| `slam_candidate_cap` | Hand-set | 3; set by the 100 ms budget |
| `open_candidate_temperature` | Hand-set | Softmax temperature over Open candidates |

## Augments

Owner: [Augment decisions](../../issues/021-augment-decisions.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `comp_defining_margin` | 2 (z = 2) | |
| `augment_tier_delta` | Hand-set | MetaTFT's map (S −0.3, A −0.15, B 0, C +0.15, D +0.3) until Set 18 statistics exist |
| `augment_prior_strength` | 3 | Once augment statistics return |
| `augment_flag_prior_multiplier` | 3 | Start 2. Dormant until augment statistics return; then set by holdout across patches: how well flagged early-patch statistics predict late-patch statistics |

## Shop, Wisp and carousel

Owner: [Shop, Wisp and carousel decisions](../../issues/023-shop-wisp-and-carousel-decisions.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `board_power_buy_min` | 2 (z = 1) | |
| `wisp_buy_margin` | 2 (z = 1) | Set-specific; dropped at a new set |

## Positioning

Owner: [Positioning decisions](../../issues/022-positioning-decisions.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `threat_share_on` | 2 | About 0.5 |
| `threat_share_off` | 2 | About 0.3 |
| `board_settle_seconds` | Hand-set | About 2 |

## Review

Owner: [Post-game review scope](../../issues/015-post-game-review-scope.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `review_min_cost` | 2 (z = 1) | Default: the larger of the estimate's standard error and 0.05 placement |

## Confidence and capture thresholds

Owners: [Advice engine architecture](../../issues/011-advice-engine-architecture.md), [Game-state capture route](../../issues/009-game-state-capture-route.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `confidence_show_min` | Hand-set | 0.2; surfaces drop advice below it |
| `confidence_medium_min` | Hand-set | 0.5; below it advice is low confidence: shown dashed and never spoken |
| `confidence_high_min` | Hand-set | 0.8; tier-based augment advice stays below it |
| `board_reader_identity_min` | Hand-set | 0.55, TFT-COACH's own acceptance floor; above it the reader's unit identity wins over purchase tracking |
| `field_max_age_seconds` | Hand-set | Per field, shared by every sub-engine: 2 s by default, 0.5 s for the shop in roll-down mode. Past it the field counts as missing |

## Not tunables

Roll-down mode's start and end thresholds (two rolls within about 2 s, about 3 s without a roll) are UX settings, not Engine tunables ([Evaluation harness](../../issues/027-evaluation-harness.md)). The scout-eye thresholds (3 rounds, about 13 %) and the 400 ms tooltip delay are fixed in [Advice surface UX](../../issues/026-advice-surface-ux.md) and not listed as tunables.

Settled in [Families for unassigned tunables](../../issues/032-families-for-unassigned-tunables.md):

- The bench priority order is a fixed rule in [sub-engines.md](sub-engines.md#shop), and the bench size is game data in the static file. There is no `hold_priority` or `bench_budget` tunable.
- The commitment triggers other than `commit_latest_round` are fixed rules.
- The threat keyword lists are per-set data in the static file ([patch-workflow.md](patch-workflow.md#static-file)). The owner override's threat-tag section still wins over derived tags.
