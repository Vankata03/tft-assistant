---
id: 12
title: "Transition and pivot domain model"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: [3, 5, 6]
---

## Question

How does the coach model a transition (interim board to final comp) and a pivot (abandoning the target comp for another)? Define the inputs each needs (own board, items, augments, gold, HP, contested units, opponents' boards, pool state), the triggers that start one, and the concrete advice it gives. Stress-test against scenarios such as a contested carry at 3-2 or a highroll that makes the interim board the final one.

## Comments

### 2026-10-04 — claude-code

Input from "Data source strategy": each Guide's static interim board comes from TFT Academy's `earlyComp` (units and items, no positions), positioned with MetaTFT's cell histogram. No source has early-board statistics, because the Riot API records only final boards. A dynamic interim board built from the units the player owns (Live mode, stages 2-1 to 3-2) must therefore be scored heuristically from static data: trait breakpoints, unit cost, star level and item fit, steered toward the Guide's target comp. This ticket owns that selection logic.

### 2026-10-04 — claude-code

Input from "Advice engine architecture": this ticket owns the Engine's Game plan layer, meaning the target comp and its Line. Comp choice, transition and pivot all live in that layer, and a pivot is a change of Game plan. Sub-engines never change the Game plan; they raise pressure signals (carry contested, augment or items fit another comp) that this layer weighs. Define the pressure signal, since "Item decisions", "Augment decisions" and "Shop, Wisp and carousel decisions" wait on it. The Engine is a pure function of the snapshot and the game history, so contested units and pool depletion must be derived from history, not stored state.

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: "Advice engine architecture", "Data source strategy", "TFT econ, level and roll math and established theory" and "Current TFT set and its mechanics, including wisp".

- **Game plan state.** The Engine derives the Game plan by folding the Game plan layer over the game history. Each call replays the layer over past snapshots, so it knows the previous plan without hidden state, and that gives hysteresis. Caching the fold is an optimization only.
- **Open and Committed.** An Open plan keeps the top-k candidate comps (k in tunables), plays the strongest board and holds flexible units. Moving between candidates while Open is free and raises no call. The plan commits at the first commitment trigger: the first finished item on a carry, a 2-star or 3-star key unit, a comp-defining augment, or stage 3-2 at the latest. The triggers live in tunables. A Committed plan has one target comp and at most one Backup comp: the second-best comp by comp fit, whose key units the shop sub-engine holds when bench space allows.
- **Comp universe.** Guides (TFT Academy plus owner overrides), each mapped to a MetaTFT cluster for statistics. A toggle, off by default, adds MetaTFT clusters that have no Guide. An unguided comp takes a default Line keyed by its carry's cost from tunables, items from MetaTFT per-unit item statistics, positioning from MetaTFT's cell histogram, and no static interim board. All advice for it carries lowered confidence.
- **Comp fit.** Every candidate comp is scored as the expected placement if the player plays it from now on. The score starts from MetaTFT's average placement and adds terms for: key-unit hit probability under the comp's Line and the visible pool, item fit, augment fit, owned progress (units and star levels), and Line feasibility against rounds left to live. Switching cost is implicit, because progress the player would sell does not count toward the new comp.
- **Pressure signal.** This is not an event. Each sub-engine contributes the comp fit term for its own domain through `fit(comp, state) → term`, a placement delta plus a reason template. Items supplies item fit, augments supplies augment fit, and econ-level-roll supplies hit probability and feasibility. The Game plan layer sums the terms and decides.
- **No hard gates.** Pivots that look impossible are scored, not filtered:
  - Item fit assigns the held finished items and components to the comp's item holders. A finished item of the wrong class (an AD item in an AP comp such as Ahri or Morgana) is worth almost nothing, while components keep their value.
  - Hit probability is computed from the current level onward. A reroll comp seen at level 7 is judged on level-7 odds and the gold that is left.
  - A comp whose key units cannot arrive before the player runs out of rounds to live gets a very poor fit.
- **Choice scoring.** A choice that could change the comp is scored as the best comp fit across candidate comps after taking that option. This covers augment picks, carousel picks and taking a component. The sub-engine still never changes the plan. If an option makes another comp best, the next check changes the plan through the normal margin.
- **Pivot.** A Committed plan pivots when the best other comp's fit beats the target comp's fit by the pivot margin. The margin is set per stage in tunables and is larger after the main roll-down. Starting values are about 0.5 placement at stage 3 and 0.8 after the roll-down; the evaluation harness tunes them. Fit is checked every planning phase, with no fixed pivot windows, and the Backup comp uses the same margin. When the margin is passed, the plan switches at once. The first advice item is "Pivot to Y", with the two largest fit-term differences as its reason. Every sub-engine's advice under Y follows: sell, buy, items and the new Line.
- **Player divergence.** A comp classifier infers the player's comp each snapshot by mapping board and bench to the closest comp in the universe. The same classifier labels opponents' boards and serves "Board and lobby strength heuristic".
  - If the player does not move toward Y for one planning phase, the plan reverts to the player's comp. The pivot call returns only past a re-raise margin: the pivot margin plus a tunable extra.
  - A pivot the player starts without a call is adopted the same way: after one planning phase on comp Z, the plan is Committed to Z.
  - A comp locked in the picker overrides the Engine's choice. Pivot advice is still given.
  - Post-game review shows the calls the player ignored.
- **Contested.** There is no separate rule; contest acts through hit probability.
  - Unit level: copies that opponents hold are removed from the pool. The count uses the latest sighting of each opponent's board, plus the bench if the capture route exposes it.
  - Comp level: the number of opponents the classifier puts on the same comp, or who hold 2 or more copies of its carry.
  - A sighting has full weight for N rounds (tunable, about 2). After that its contested term fades and advice confidence drops.
  - With no opponent data there is no contested term. The coach never infers contest from the player's own shop.
- **Transition.** Each planning phase the Engine computes a recommended board: the owned units (board and bench) within the unit cap that give the highest board strength, scored by the heuristic from "Board and lobby strength heuristic". Progress toward the target comp only breaks ties within a strength tolerance from tunables.
  - Transition is strength-gated. A comp unit replaces an interim unit only when the board stays at least as strong, within the tolerance.
  - The deadline is the main roll-down in the comp's Line (for example 4-2 for fast 8, 3-1 for reroll), or the owner override's deadline. Past it, the board takes the comp's units even at some loss of strength.
  - Advice is the difference from the current board: "Swap X for Y", "Hold Y" (within a bench budget that includes Backup comp units) and "Sell X".
  - Item holders belong to "Item decisions"; placement belongs to "Positioning decisions".
- **Scenarios checked.**
  - Contested carry at 3-2: Ahri's hit-probability term drops and a comp that shares AP items leads. Past the margin, the coach calls "Pivot to Morgana" with the hit-odds difference as its reason.
  - Highroll 3-star 2-cost unit at 2-5: the plan commits to a reroll Guide if one uses the unit as its carry. Otherwise the strength gate keeps the unit until it is outclassed or the deadline passes.
  - Full AD items with an AP augment on offer: the best fit after taking the augment is still the AD comp, so the augment ranks low and no pivot follows.
  - Missed roll-down at 4-2 on 30 HP: the larger margin and poor feasibility of every alternative keep the plan, and econ-level-roll decides whether to keep rolling. No separate "play strongest board" plan is needed, because the transition gate already plays the strongest owned board.
- **Baseline mode** is unchanged. The Guide lists pivot alternatives before the game, and the player decides.

Glossary terms Open, Committed, Backup comp, Comp fit, Pivot margin, Recommended board and Unguided comp added to `CONTEXT.md`; Game plan sharpened.

Input posted to "Item decisions", "Augment decisions", "Shop, Wisp and carousel decisions", "Econ, level and roll Line simulation", "Board and lobby strength heuristic", "Positioning decisions", "Game-state capture route", "Probe live game data sources in a real TFT game" and "Post-game review scope".

### 2026-10-04 — claude-code

Input from "Econ, level and roll Line simulation": this amends the comp fit terms. For comps the econ, level and roll sub-engine simulates (the target comp, the Backup comp and the top challengers from an analytic screen), the best Line's simulated expected placement is the backbone of comp fit, and comp fit equals that value plus item fit plus augment fit. Owned progress, key-unit hit probability and Line feasibility are inside the simulated result and are not added again; they survive only as its reason decomposition. Comps that are only screened keep the additive form above.

### 2026-10-04 — claude-code

Input from "Board and lobby strength heuristic": the recommended board is scored with board power, an additive sum of unit, trait-breakpoint and generic item terms. Trait breakpoints make the sum non-additive across units, so picking the best subset of owned units within the unit cap needs a search. Exhaustive search over a full bench (about 48,000 subsets at level 9) is near the 100 ms budget, so the build should use greedy selection with swap improvement. That is a build detail, not a decision.
