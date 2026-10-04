# Tunables index

Part of the [MVP spec](../spec.md). Every number and threshold the Engine uses lives in the per-patch tunables file `data/<patch>/` (TOML), which the owner override file can change ([Advice engine architecture](../../issues/011-advice-engine-architecture.md)). Families come from [Evaluation harness](../../issues/027-evaluation-harness.md):

- **1, fitted** on game logs by maximum likelihood and gated.
- **2, margin**, set from noise: z times the standard error of the difference it guards, z = 2 for costly or sticky calls and 1 for cheap or reversible ones.
- **3, prior**, set from public statistics by empirical Bayes or holdout.
- **Hand-set**, report only, because no v1 data can set it.
- **Unassigned**: no ticket gave a family. These are open in [Families for unassigned tunables](../../issues/032-families-for-unassigned-tunables.md).

Names in `code font` were named by their ticket. Plain-text entries were described only in prose; the build or ticket 32 names them.

Static-file values (XP, gold, streak, interest and damage tables, shop odds, pool sizes, rules flags, Wisp effects, econ augment tags, tier pools, opening encounters) are game data, not tunables; see [patch-workflow.md](patch-workflow.md#static-file).

## Game plan, transition and pivot

Owner: [Transition and pivot domain model](../../issues/012-transition-and-pivot-model.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| Pivot margin per stage | 2 (z = 2) | Starting floors about 0.5 placement at stage 3 and 0.8 after the main roll-down |
| Pivot re-raise extra | 2 | Added to the pivot margin before a reverted pivot call returns |
| k, the number of Open candidate comps | Unassigned | |
| Commitment triggers | Unassigned | First finished item on a carry, 2-star or 3-star key unit, comp-defining augment, stage 3-2 at the latest |
| Rounds a sighting keeps full weight | Unassigned | About 2 |
| Transition strength tolerance | Unassigned | Ties within it are broken by progress toward the target comp |

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
| `gold_floors` | Unassigned | 50, 30, 10, 0 |
| `all_in_rounds_left` | Unassigned | Below it, floor 0 is always a candidate |
| `stabilize_rounds_left` | Unassigned | Below it, the stabilize Line joins the candidates |
| `default_lines_by_carry_cost` | Unassigned | Lines for unguided comps |

## Board power and lobby strength

Owner: [Board and lobby strength heuristic](../../issues/019-board-and-lobby-strength-heuristic.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `unit_weight`, `trait_weight`, `item_weight` | 1 | Fitted on the owner's final boards, then on game logs |
| Fight scale | 1 | Initial k in `win_probability` |
| `win_scale_by_stage` | 1 | Per-stage k, split from the pooled value past about 150 fights at a stage |
| `survivor_scale_by_stage` | 1 | c in `surviving_units` |
| `cost_star_baseline` | 3 | Fallback unit-star power for thin samples |
| `unit_prior_strength` | 3 | Shrinkage sample size for unit power |
| `item_values` | Unassigned | Finished item, component, cost-3+ bonus |
| `classifier_weights` | Unassigned | Carry ×3, key units ×2, others ×1, bench at half weight |
| `classifier_threshold` | Unassigned | Below it the label is "no comp" |

## Opponent model

Owner: [Opponent model from trait-only sightings](../../issues/030-opponent-model-from-trait-only-sightings.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `opponent_star_mix` | 1 | Share of 1-, 2- and 3-star units by round and unit cost, fitted on the owner's own boards in game logs; a hand default table until logs exist |
| `emblem_count_prior` | 1 | Fitted on match final boards, then on game logs |
| `size_level_prior` | 1 | Distinct units against level; fitted like `emblem_count_prior` |
| `emblem_slack_max` | Hand-set | 2; trait counts the solver may assign to emblems |
| `sighting_persistence_weight` and its fade | Unassigned | Prior boost for units on the opponent's previous inferred board |

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
| `augment_flag_prior_multiplier` | Unassigned | Applies once statistics return |

## Shop, Wisp and carousel

Owner: [Shop, Wisp and carousel decisions](../../issues/023-shop-wisp-and-carousel-decisions.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `board_power_buy_min` | 2 (z = 1) | |
| `wisp_buy_margin` | 2 (z = 1) | Set-specific; dropped at a new set |
| `hold_priority` | Unassigned | The bench priority order |
| `bench_budget` | Unassigned | |

## Positioning

Owner: [Positioning decisions](../../issues/022-positioning-decisions.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `threat_share_on` | 2 | About 0.5 |
| `threat_share_off` | 2 | About 0.3 |
| `board_settle_seconds` | Hand-set | About 2 |
| Threat keyword lists | Unassigned | Per tag; the owner override's threat-tag section wins over derived tags |

## Review

Owner: [Post-game review scope](../../issues/015-post-game-review-scope.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| `review_min_cost` | 2 (z = 1) | Default: the larger of the estimate's standard error and 0.05 placement |

## Confidence and capture thresholds

Owners: [Advice engine architecture](../../issues/011-advice-engine-architecture.md), [Game-state capture route](../../issues/009-game-state-capture-route.md).

| Tunable | Family | Notes |
| --- | --- | --- |
| Confidence threshold below which surfaces drop advice | Unassigned | |
| Voice's stricter confidence threshold | Unassigned | |
| Board-reader confidence threshold for unit identity | Unassigned | Above it the reader's identity wins over purchase tracking. TFT-COACH's own acceptance floor is 0.55 |
| Maximum field age per sub-engine and field | Unassigned | Past it the field counts as missing |

## Not tunables

Roll-down mode's start and end thresholds (two rolls within about 2 s, about 3 s without a roll) are UX settings, not Engine tunables ([Evaluation harness](../../issues/027-evaluation-harness.md)). The scout-eye thresholds (3 rounds, about 13 %) and the 400 ms tooltip delay are fixed in [Advice surface UX](../../issues/026-advice-surface-ux.md) and not listed as tunables.
