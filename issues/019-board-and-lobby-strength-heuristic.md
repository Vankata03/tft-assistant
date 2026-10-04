---
id: 19
title: "Board and lobby strength heuristic"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: []
---

## Question

How does the Engine score a board's strength and the player's position in the lobby without a trained model? "Advice engine architecture" fixed the approach: match the board to the closest MetaTFT comp, start from its average placement, and adjust for completeness (units against level, star levels, finished items); lobby position ranks the player's score against opponents' scores in Live mode, with HP as the fallback. Decide the matching rule for boards that fit no comp, the completeness adjustments and their weights, how scouted or partial opponent data is handled, and how the win-chance estimate shown in Baseline mode relates to this score. This is the Engine's weakest part, so also decide how its error will be measured against recorded games.

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": the transition logic scores many subsets of owned units each snapshot to pick the recommended board (the strongest board within the unit cap), so the strength score must handle arbitrary partial boards, including boards that fit no comp, and must be cheap. The comp classifier that maps a board (and bench) to the closest comp is shared: it infers the player's current comp for the Game plan and labels opponents' boards for the contested count.

### 2026-10-04 — claude-code

Input from "Econ, level and roll Line simulation": the Line simulator calls this heuristic through four functions, which this ticket must define: `strength(board, level) → score`; `placement(own score, opponent scores, HP) → expected placement`, which values the simulation's terminal state, with death before the horizon mapped by the expected elimination order; `win_probability(own score, opponent score, stage)` for each simulated fight; and `surviving_units(score gap, stage)` for the damage of a loss. Terminal strength counts units, stars and level and holds items out, because item fit is added separately. The simulator also needs an `opponent_growth_curve` in tunables: how a typical opponent's strength grows per round by stage, used to advance each opponent from their last sighting and as the lobby average when no opponent data exists. Every call runs inside Monte Carlo rollouts for several comps and Lines, so the functions must be cheap.

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: "Advice engine architecture", "Transition and pivot domain model", "Econ, level and roll Line simulation", "Data source strategy", "TFT stats data sources and their APIs" and "Policy stance and feature modes".

- **Board power, not placement.** `strength(board, level)` returns board power: one absolute number on the same scale at every stage, so any two boards compare by subtraction. Placement and fight odds are derived from it. The opponent growth curve is expressed in board power per round.
- **Additive model.** This amends "Advice engine architecture", which matched a board to its closest MetaTFT comp first. Board power is the sum of unit power over the units on the board, a trait term over active breakpoints, and a generic item term. One formula covers every board, including interim boards and boards that fit no comp, and it is cheap enough for transition's subset scoring and the Line simulator's rollouts. Level enters only through the units it allows. There is no comp-coherence bonus, because unit and trait values already carry it.
- **Unit power.** Each unit-star has its own value, taken from tactics.tools per-unit star splits (MetaTFT as fallback): the logit of its top-4 rate minus the lobby average. Unit-stars with thin samples (3-star 4-costs, units new or changed this patch) shrink toward a cost-and-star baseline from tunables, weighted by sample size. The baseline is a fallback only. Values refresh with the statistics, under the patch-day rules of "Data source strategy". Known weakness: a unit's split partly reflects the strength of the comp it usually sits in. The fight-log metric below shows where that misleads.
- **Trait term.** A bonus per active breakpoint from tactics.tools trait-breakpoint statistics, with the same logit transform.
- **Item term.** Generic item power: a flat value per finished item and per component on the board, plus a small bonus for an item on a unit of cost 3 or more. It is the same for every comp. Comp-specific item fit (the right item on the right carry) stays in "Item decisions" alone. This amends "Econ, level and roll Line simulation": terminal strength holds items generic, not out. The simulator holds the player's items fixed across Lines and comps, so the generic term cancels when comps are compared.
- **Global weights.** Three scalars (unit weight, trait weight, item weight) and the fight scale are fitted against the final boards of the owner's own matches: about 800 boards from 100+ matches, fetched with the personal key. The fit has only a handful of parameters, so the owner's matches suffice, and the trait weight corrects any double counting between unit and trait values. The weights are refitted as new matches arrive. No Riot crawler is added; "Data source strategy" stands.
- **`win_probability(own, opponent, stage)`** = σ(k_stage · (own power − opponent power)). The initial k is the fitted fight scale, the same for every stage. Per-stage k is tuned from fight logs.
- **`placement(own power, opponent powers, HP)`** = 1 + Σ over alive opponents of P(opponent outlasts the player), where P = σ(a · (opponent power − own power) + b · (opponent HP − own HP) / stage damage). The HP gap is measured in lost rounds. `b` is `terminal_hp_weight` from "Econ, level and roll Line simulation". Dead opponents rank below the player.
- **`surviving_units(power gap, stage)`** = the winner's unit count × σ(c_stage · gap). Damage on a loss is the stage base plus the per-unit damage of the survivors from the static file.
- **`opponent_growth_curve`** is computed, not hand-typed: typical board power per round = the units allowed by a standard level calendar × the average unit-star power under that level's shop odds, plus the stage-typical generic item term. It is recomputed when the statistics refresh and corrected against scouted boards once capture exists. This amends its listing as a hand-set tunable in "Econ, level and roll Line simulation".
- **Comp classifier.** Shared by Game plan inference, opponent labels and the contested count; it no longer feeds strength. Similarity is the weighted overlap between the board's units and a comp's final units: the carry ×3, other key units ×2, other units ×1, and the player's bench at half weight. Stars are ignored. It returns the top comps with their similarity. Below a threshold the label is "no comp". Open plans read the top-k list; the contested count uses only labels above the threshold. Early boards rarely classify, which is correct.
- **Partial and stale opponent data.** Stale sightings advance along the growth curve (settled in "Transition and pivot domain model"). Missing fields are imputed at the stage average and nothing seen is replaced: unseen items become the stage-average item term, and empty slots below the opponent's level become average-power units for that level's shop odds. Each imputation lowers the confidence of the advice that depends on it. An opponent never seen is the growth curve.
- **Baseline mode win chance.** Per opponent: `win_probability` against each opponent the player could meet next, from their last sighting, as MetaTFT's approved app shows. Baseline mode shows the number only, never an action drawn from it.
- **Error measurement**, in order of availability:
  1. Final-board ranking on the owner's matches, available now: Spearman rank correlation of board power with placement, and mean absolute error of `placement()` against actual placement.
  2. Round fights from captured game logs: Brier score and log-loss of `win_probability`, with a calibration curve by stage.
  3. Damage from captured game logs: mean absolute error of predicted against actual HP loss per lost round.
- **Tunables owned here:** `cost_star_baseline`, `unit_prior_strength` (the shrinkage sample size), `item_values` (finished, component, cost-3+ bonus), `win_scale_by_stage`, `survivor_scale_by_stage`, `classifier_weights`, `classifier_threshold`, and the fitted `unit_weight`, `trait_weight`, `item_weight` and fight scale.

Glossary terms Board power and Win chance added to `CONTEXT.md`.

Input posted to "Advice engine architecture" and "Econ, level and roll Line simulation" (amendments), "Game-state capture route" (fight and damage logging), "Probe live game data sources in a real TFT game" (survivor damage), "Transition and pivot domain model" (subset scoring cost) and "Post-game review scope" (the error metrics).
