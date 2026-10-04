---
id: 20
title: "Item decisions"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: [12]
---

## Question

How does the item sub-engine decide component allocation and when to slam a finished item? It reads the Game plan's target comp and the Guide's best-in-slot items, and is greedy (no lookahead). Decide how components are assigned when the target comp's items cannot all be built, when slamming a non-best-in-slot item beats holding components (HP, streak, stage), how item holders on the interim board hand items to the carry during a transition, and when item fit raises a pressure signal for a pivot.

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": the item pressure signal is the item fit term this sub-engine contributes to comp fit through `fit(comp, state) → term`, a placement delta plus a reason template. Item fit assigns held finished items and components to a comp's item holders. A finished item of the wrong class (AD in an AP comp) is worth almost nothing, while components keep their full value. Taking a component, like any choice that could change the comp, is scored as the best comp fit across candidate comps after the choice. Item holders on the interim board, and how they hand items over during a transition, belong to this ticket; transition advice covers only which units are fielded, held and sold.

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: "Transition and pivot domain model", "Advice engine architecture", "Econ, level and roll Line simulation", "Board and lobby strength heuristic", "Data source strategy" and "Riot third-party app policy for real-time TFT advice".

Item rules assumed for Set 18, to be confirmed by "Probe live game data sources in a real TFT game": a finished item stays on its unit until the unit is sold (its items return to the item bench) or a Magnetic Remover takes them off; a single component can sit on a unit and gives its stats, and a second component combines in place.

- **Item value.** The value of item X on unit Y comes from MetaTFT's per-unit item statistics (`unit_items_processed`): the unit's average placement with the item minus its average placement overall. Thin samples shrink toward a class prior (AD, AP, tank, utility) from tunables, weighted by sample size. The class prior gives the settled rule that a wrong-class finished item is worth almost nothing. A holder's items add up; 3-item build statistics are too sparse for v1. The Guide's best-in-slot items pick the item holders and break ties. Emblems, artifacts, Radiant and support items are valued the same way; item kinds with no statistics fall back to the class prior with lowered confidence.
- **Item holders.** Each comp has a fixed list of at most 3 item holders: the units that carry items in the Guide's `finalComp`, or for an unguided comp the 2 or 3 units with the highest item frequency in its MetaTFT cluster. The owner override wins.
- **Item fit.** The term this sub-engine contributes to comp fit through `fit(comp, state) → term`. It is the value of the best assignment of the player's finished items and components to the comp's holders, minus a reference: the frequency-weighted average value of the items each holder carries in MetaTFT statistics. A typical item set scores about 0, best-in-slot scores above 0, and wrong-class items score below 0. This keeps item fit a delta on top of the MetaTFT comp average that already sits inside the simulated placement.
- **Components.** An unfinished component counts at its option value: the expected value of the best item it can still finish, given the other held components and the expected future components by stage (a component income curve in tunables), discounted as the game ages to about 0 by stage 5. Assignment is an exhaustive search; with about 10 components, 3 holders and the recipe table it is small.
- **Slam versus hold.** Building a finished item now (best-in-slot or not), or placing a single component on a unit, is valued like a Wisp: the Line simulator runs the current best Line twice with the same seed, once with the item built and once with the components held, and the difference is the tempo value (HP saved, streak kept). The sub-engine adds the change in item fit and calls the slam if the sum is positive. At most 3 slam candidates are simulated per snapshot. This is a one-step evaluation, not a search, so the sub-engine stays greedy.
- **Interim holders.** A finished item goes on its comp holder if that unit is owned and fielded. Otherwise it goes on an interim unit, chosen for the most board power now and the right item class. Without a remover in hand, an interim holder must be a unit the comp will sell; an item is never locked on a comp unit that is not its holder. With k removers held, up to k units that stay on the board, including non-holder comp units, may hold items when that gives more board power.
- **Handover.** When the recommended board drops an interim holder, the transition advice carries the items: "Sell X, items to Y". When the holder Y is fielded and the unit carrying its items stays in the recommended board, the advice is "Use remover on X, items to Y", given that the move raises item fit plus board power. Removers are spent greedily, with no reserve rule. A remover on offer is scored by the settled choice rule.
- **Open Game plan.** While the plan is Open, items are allocated to maximize item fit across the top-k candidate comps, weighted by each candidate's share (a softmax of comp fit, temperature in tunables). This favours items that fit several candidates. A finished item on a carry is a commitment trigger, so the weighting keeps a slam from committing to a weak candidate; items on interim holders that will be sold do not commit the plan.
- **Choices and tools.** Item anvils, Item-category Wisps, artifact picks and removers on offer are scored by the best comp fit across candidate comps after the choice. Reforger is advised only for a wrong-class finished item when reforging raises item fit.
- **Pivot pressure.** Item fit is the item pressure signal; the Game plan layer sums it with the other terms and pivots through the pivot margin. Nothing else is added.
- **Advice.** Live mode: "Build X on Y", "Place component on Y", "Hold components", "Sell X, items to Y", "Use remover on X, items to Y", "Reforge X" and "Take X", each with item fit and tempo numbers in the reason. Baseline mode: the chosen comp's best-in-slot items and recipes from its Guide, with the held components that build them highlighted, and no slam calls. Post-game review replays slams and holder choices through the same rules.
- **Required fields.** Items on the player's units and the item bench. If the capture route lacks the item bench, the sub-engine emits nothing. Opponents' items are not used here; board power imputes them.
- **Tunables owned here:** `item_class_prior`, `item_prior_strength`, `component_income_by_stage`, `component_discount_by_stage`, `slam_candidate_cap` (3) and `open_candidate_temperature`.

Glossary terms Item holder, Best-in-slot, Item fit and Slam added to `CONTEXT.md`.

Input posted to "Econ, level and roll Line simulation" (paired runs with different item states), "Shop, Wisp and carousel decisions" (item choices), "Game-state capture route" (required fields), "Probe live game data sources in a real TFT game" (item rules to confirm) and "Post-game review scope".
