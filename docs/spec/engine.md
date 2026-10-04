# The Engine

Part of the [MVP spec](../spec.md). Sources: [Prior art for TFT decision engines and the train-vs-LLM question](../../issues/007-decision-engine-prior-art.md), [TFT econ, level and roll math and established theory](../../issues/006-econ-level-roll-theory.md), [Advice engine architecture](../../issues/011-advice-engine-architecture.md), [Transition and pivot domain model](../../issues/012-transition-and-pivot-model.md), [Econ, level and roll Line simulation](../../issues/018-econ-level-roll-line-simulation.md), [Board and lobby strength heuristic](../../issues/019-board-and-lobby-strength-heuristic.md).

The sub-engines are in [sub-engines.md](sub-engines.md).

## Contract

- **Deterministic.** Rules, game maths, statistics and Guides decide all advice. No trained decision model and no language model is used in v1. Advice text and review prose come from templates.
- **Objective.** The Engine optimizes expected placement, matching the success measure. HP is a resource, converted to rounds left to live, not a goal.
- **Pure function.** `advise(game snapshot, game history, data snapshot, mode) → advice list`, with no hidden state. Derived beliefs, such as pool depletion, contested units, streak, the Game plan and the advised Line, are computed from the history passed in. Random draws use a seed derived from the snapshot, so output is reproducible. Live mode calls it on each state change; post-game review replays the game log through the same function.
- **Budget.** CPU only, 100 ms per snapshot on the Ryzen 7 7800X3D. The GPU is left to the game.
- **Two layers.** The Game plan layer owns the target comp and its Line; comp choice, transition and pivot live there. One sub-engine per decision (econ, level and roll; shop; Wisp; items; augments; positioning; carousel) reads the Game plan and the state and emits advice. A sub-engine never changes the Game plan; it contributes its comp fit term, which the Game plan layer weighs. This keeps advice from contradicting itself, such as items for one comp and shop buys for another.
- **Lookahead.** Only the econ, level and roll sub-engine looks ahead, through the Line simulator. Item slams, econ augments and Wisps borrow the simulator through same-seed pairs. Everything else is greedy.

### Advice items

Each advice item carries:

- a decision type and an action;
- an urgency: act this phase, soon, or information;
- a confidence;
- a reason, as a template plus numbers ("62 % to hit");
- a validity: the state change that ends it.

The Engine returns the list ranked by urgency, then by impact on expected placement. Surfaces choose only how many items to show; they never re-rank. Surfaces drop items below a confidence threshold, and voice uses a stricter threshold than the overlay.

### Missing and flagged data

Each sub-engine declares its required fields and stays silent when one is missing or stale; it never guesses. Stale, "changed this patch", `default` and `carried` data lower confidence ([data.md](data.md), [patch-workflow.md](patch-workflow.md)).

### Heuristics as data

Logic lives in code. Every number and threshold lives in the per-patch tunables file beside the static file, and the owner override file can change them. Patch day is a data edit, not a code change. The index is in [tunables.md](tunables.md).

### Mode separation

The Engine core always ships, because post-game review runs it in both modes. The Live advisor, the in-game loop that feeds live snapshots to the Engine and surfaces its advice, is the separable Live-mode component. In Baseline mode, in-game features are the Guide layer (static, stage-keyed), shop highlighting and the grey-zone hints. Which Engine functions those hints may call in-game is open: [Baseline mode and opponent sightings](../../issues/031-baseline-mode-and-opponent-sightings.md).

## Game plan

### State

The Engine derives the Game plan by folding the Game plan layer over the game history. Each call replays the layer over past snapshots, so it knows the previous plan without hidden state, and that fold gives hysteresis. Caching the fold is an optimization only.

- **Open.** The plan keeps the top-k candidate comps (k in tunables), the strongest board is played, and flexible units are held. Moving between candidates while Open is free and raises no call.
- **Committed.** The plan commits at the first commitment trigger: the first finished item on a carry, a 2-star or 3-star key unit, a comp-defining augment, or stage 3-2 at the latest. The triggers live in tunables. A Committed plan has one target comp and at most one Backup comp, the second-best comp by comp fit, whose key units the shop holds when bench space allows.
- **First candidates.** The Open plan's first top-k candidates at 1-1 are ranked by comp fit, which at that point is mostly the MetaTFT average, plus the item fit of held components, plus the opening encounter's effect. There is no separate opener logic.

### Comp universe

The universe is the Guides (TFT Academy plus owner overrides), each mapped to a MetaTFT cluster for statistics. A toggle, off by default, adds MetaTFT clusters without a Guide. An unguided comp takes a default Line keyed by its carry's cost, items from MetaTFT per-unit item statistics, positioning from MetaTFT's cell histogram and no static interim board. All advice for it carries lowered confidence.

### Comp fit

Comp fit is the expected placement if the player plays a comp from now on.

- **Simulated comps** (the target, the Backup and the top challengers, or the top-k candidates while Open): comp fit = the best Line's simulated expected placement + item fit + augment fit. Owned progress, key-unit hit probability and Line feasibility are inside the simulated result and are not added again. They survive as its reason decomposition, for example "Ahri: 41 % to 2-star by 4-2 (−0.6), 18 % dead before 4-2 (−0.3)".
- **Screened comps** keep an additive form: MetaTFT's average placement plus terms for key-unit hit probability under the comp's Line and the visible pool, item fit, augment fit, owned progress, and Line feasibility against rounds left to live.
- **Interface.** Each sub-engine contributes its domain's term through `fit(comp, state) → term`, a placement delta plus a reason template. Items supply item fit, augments supply augment fit, and the Line simulator supplies the simulated placement. The Game plan layer sums the terms and decides. This replaces any separate pressure signal.
- **Switching cost is implicit.** Progress the player would sell does not count toward the new comp.
- **No hard gates.** Pivots that look impossible are scored, not filtered: a wrong-class finished item is worth almost nothing while components keep their value; hit probability is computed from the current level onward; a comp whose key units cannot arrive before the player runs out of rounds to live gets a very poor fit.
- **Choice scoring.** A choice that could change the comp (an augment, a carousel pick, a component, a unit-granting Wisp) is scored as the best comp fit across candidate comps after taking that option. The sub-engine still never changes the plan; if an option makes another comp best, the next check changes the plan through the normal margin.

### Pivot

- A Committed plan pivots when the best other comp's fit beats the target comp's fit by the pivot margin. The margin is set per stage and is larger after the main roll-down; starting values are about 0.5 placement at stage 3 and 0.8 after the roll-down. The Backup comp uses the same margin.
- Fit is checked every planning phase, with no fixed pivot windows. Past the margin the plan switches at once. The first advice item is "Pivot to Y", with the two largest fit-term differences as its reason. Every sub-engine's advice then follows Y: sells, buys, items and the new Line.
- **Player divergence.** The comp classifier infers the player's comp each snapshot.
  - If the player does not move toward Y for one planning phase, the plan reverts to the player's comp. The pivot call returns only past a re-raise margin: the pivot margin plus a tunable extra.
  - A pivot the player starts without a call is adopted the same way: after one planning phase on comp Z, the plan is Committed to Z.
  - A comp locked in the picker overrides the Engine's choice. Pivot advice is still given.
- Post-game review shows pivot calls the player ignored and pivots taken without a call.
- **Baseline mode** lists pivot alternatives from the Guide before the game, and the player decides.

### Contested

There is no separate contest rule; contest acts only through hit probability.

- Unit level: copies that opponents hold are removed from the pool, counted from each opponent's latest sighting (plus the bench, if the route exposed it).
- Comp level: the number of opponents the classifier puts on the same comp, or who hold 2 or more copies of its carry.
- A sighting has full weight for about 2 rounds (tunable). After that its contested term fades and advice confidence drops.
- With no opponent data there is no contested term. The coach never infers contest from the player's own shop.

Sightings in v1 carry traits only, so the unit-level and comp-level counts above have no units to count. How they work from traits is open: [Opponent model from trait-only sightings](../../issues/030-opponent-model-from-trait-only-sightings.md).

### Transition

- Each planning phase the Engine computes the recommended board: the owned units (board and bench) within the unit cap that give the highest board power. Progress toward the target comp only breaks ties within a strength tolerance. Because trait breakpoints make the sum non-additive, the build picks the subset by greedy selection with swap improvement; exhaustive search over a full bench is near the 100 ms budget.
- Transition is strength-gated: a comp unit replaces an interim unit only when the board stays at least as strong, within the tolerance.
- The deadline is the main roll-down in the comp's Line (for example 4-2 for fast 8, 3-1 for reroll), or the owner override's deadline. Past it, the board takes the comp's units even at some loss of strength.
- Advice is the difference from the current board: "Swap X for Y", "Hold Y" (within the bench budget in [sub-engines.md](sub-engines.md#shop)) and "Sell X". Item handover belongs to the item sub-engine; placement belongs to positioning.
- No separate "play strongest board" plan exists, because the strength gate already plays the strongest owned board.

### Scenarios checked

- **Contested carry at 3-2.** Ahri's hit term drops and a comp that shares AP items leads. Past the margin the coach calls "Pivot to Morgana" with the hit-odds difference as its reason.
- **Highroll 3-star 2-cost at 2-5.** The plan commits to a reroll Guide if one uses that unit as its carry. Otherwise the strength gate keeps the unit until it is outclassed or the deadline passes.
- **Full AD items with an AP augment on offer.** The best fit after taking the augment is still the AD comp, so the augment ranks low and no pivot follows.
- **Missed roll-down at 4-2 on 30 HP.** The larger margin and the poor feasibility of every alternative keep the plan. The Line simulator decides whether to keep rolling.

## Board power

Board power is one absolute number for a board's combat strength, on the same scale at every stage, so any two boards compare by subtraction. Placement and fight odds are derived from it. No trained model is used.

### Formula

Board power is the sum of three terms, combined by three global weights (`unit_weight`, `trait_weight`, `item_weight`):

- **Unit power.** Each unit-star has its own value from tactics.tools per-unit star splits (MetaTFT as fallback): the logit of its top-4 rate minus the lobby average. Thin samples (3-star 4-costs, units new or changed this patch) shrink toward a cost-and-star baseline, weighted by sample size. Known weakness: a unit's split partly reflects the comp it usually sits in; the fight-log metric shows where that misleads.
- **Trait term.** A bonus per active breakpoint, from tactics.tools trait-breakpoint statistics with the same logit transform.
- **Item term.** Generic item power: a flat value per finished item and per component on the board, plus a small bonus for an item on a unit of cost 3 or more. It is the same for every comp. Comp-specific item fit belongs to the item sub-engine alone.

Level enters only through the units it allows. There is no comp-coherence bonus. The weights and the fight scale are fitted against the final boards of the owner's own matches (about 800 boards from 100+ matches) and refitted as matches arrive. The trait weight corrects any double counting between unit and trait values.

### Interface functions

The Line simulator and the rest of the Engine call four functions. All are cheap, because they run inside Monte Carlo rollouts.

- `strength(board, level)` → board power.
- `win_probability(own, opponent, stage)` = σ(k_stage · (own power − opponent power)). Initial k is the fitted fight scale, the same for every stage; per-stage k is tuned from fight logs.
- `placement(own power, opponent powers, HP)` = 1 + Σ over alive opponents of P(opponent outlasts the player), where P = σ(a · (opponent power − own power) + b · (opponent HP − own HP) / stage damage). The HP gap is measured in lost rounds; `b` is `terminal_hp_weight`. Dead opponents rank below the player.
- `surviving_units(power gap, stage)` = the winner's unit count × σ(c_stage · gap). Damage on a loss is the stage base plus the per-unit damage of the survivors from the static file.

The **opponent growth curve** gives typical board power per round: the units a standard level calendar allows × the average unit-star power under that level's shop odds, plus the stage-typical generic item term. It is computed from statistics, recomputed when statistics refresh, and corrected against sightings once game logs exist.

### Comp classifier

The comp classifier serves Game plan inference, opponent labels and the contested count; it does not feed board power. Similarity is the weighted overlap between a board's units and a comp's final units: the carry ×3, other key units ×2, other units ×1, and the bench at half weight. Stars are ignored. It returns the top comps with their similarity; below a threshold the label is "no comp". Open plans read the top-k list. The contested count uses only labels above the threshold. Early boards rarely classify, which is correct.

### Partial and stale opponent data

- Stale sightings advance along the growth curve.
- Missing fields are imputed at the stage average, and nothing seen is replaced: unseen items become the stage-average item term, and empty slots below the opponent's level become average-power units for that level's shop odds. Each imputation lowers the confidence of the advice that depends on it.
- An opponent never seen is the growth curve.

This section assumes a sighting gives units and star levels. v1 sightings give traits only; see [Opponent model from trait-only sightings](../../issues/030-opponent-model-from-trait-only-sightings.md).

### Win chance

Win chance is `win_probability` against each opponent the player could meet next (the lobby minus recently met players), from their last sighting. Baseline mode shows the number only, never an action drawn from it, as MetaTFT's approved app does. Its status in Baseline mode is open ([Baseline mode and opponent sightings](../../issues/031-baseline-mode-and-opponent-sightings.md)).

### Error measurement

In order of availability:

1. Final-board ranking on the owner's matches, available now: Spearman rank correlation of board power with placement, and mean absolute error of `placement()` against actual placement.
2. Round fights from game logs: Brier score and log-loss of `win_probability`, with a calibration curve by stage.
3. Damage from game logs: mean absolute error of predicted against actual HP lost per lost round.

Gates on these metrics are in [review-and-harness.md](review-and-harness.md#evaluation-harness).
