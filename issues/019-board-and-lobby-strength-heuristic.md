---
id: 19
title: "Board and lobby strength heuristic"
labels: [wayfinder:grilling]
status: open
assignee:
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
