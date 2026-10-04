---
id: 18
title: "Econ, level and roll Line simulation"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: []
---

## Question

How does the econ, level and roll sub-engine choose between candidate Lines? "Advice engine architecture" fixed the method: simulate a few candidate Lines (the Guide's Line, one level earlier or later, roll-down now versus next stage) to the end of the next stage over the XP and gold calendar, hit odds and the damage model, scored by expected placement. Decide which candidates are generated and when, how hit odds account for contested units and Wisp shops, how HP and rounds left to live set roll depth, how a simulated outcome converts to expected placement, and which thresholds go into the per-patch tunables file. Stress-test against a 3-2 roll-down at 40 HP and a fast-8 Line on a loss streak.

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": this sub-engine supplies two comp fit terms for every candidate comp, not only the target: key-unit hit probability under the comp's Line, and Line feasibility against rounds left to live. Hit probability is computed from the current level onward, over the pool minus copies seen on opponents' boards; a sighting has full weight for about 2 rounds, then fades. With no opponent data, the pool is not reduced. Because it runs for several comps per snapshot, its per-comp cost matters against the 100 ms budget. The missed roll-down at 4-2 (keep rolling or not) is decided here.

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: "Advice engine architecture", "Transition and pivot domain model", "TFT econ, level and roll math and established theory" and "Current TFT set and its mechanics, including wisp".

- **Method.** Seeded Monte Carlo with common random numbers. Each candidate Line runs N rollouts to the end of the next stage, and every Line sees the same random shops and fights, so noise cancels when Lines are compared. The seed derives from the snapshot, so output is deterministic and post-game review reproduces it. Monte Carlo keeps the variance that decides death at low HP, which an expected-value model would flatten. The closed-form shop Markov chain stays as a cheap helper for screening and for "62 % to hit" reason text.
- **Line representation.** A Line is a schedule over the remaining rounds: a level target per round, and a set of roll-down rounds, each with a gold floor (roll until the key units are hit or the floor is reached). Outside a roll-down, econ holds interest and buys XP only to meet the level targets.
- **Candidates**, regenerated every planning phase, deduplicated and capped at about 7:
  1. The Guide's Line (for an unguided comp, the default Line for its carry's cost).
  2. The next level step one stage-round earlier.
  3. The next level step one stage-round later.
  4. Roll-down now, at the current level.
  5. Roll-down at the next Line point.
  6. Hold: econ to 50, level only.
  7. Stabilize, only when rounds left to live fall below a threshold: roll now to the floor that buys the strongest board, ignoring the target comp's key units.
- **Roll depth is emergent.** Roll-down candidates carry several gold floors (50, 30, 10 and 0 in tunables), and the simulation picks the best. Low HP raises the cost of losses and death, so deeper floors win without an HP-to-floor table. Below an all-in rounds-left-to-live threshold, floor 0 is always among the candidates.
- **No deliberate loss streak.** The coach never advises playing to lose. Streak is the outcome of playing the recommended board, and the path-dependent simulation prices the streak gold that a stronger board gives up.
- **Hit odds.** The pool loses only copies seen on opponents' boards, and sightings fade after about 2 rounds (settled in "Transition and pivot domain model"). Opponents' future buys are not projected. A shop's champion slot count (5, or 4 with a Wisp) comes from the capture route when known; otherwise 4.5 is assumed. Wisps not yet offered are ignored. The Wisp sub-engine values a Wisp on offer with a gold, XP or roll effect through this simulator: the simulated Line value with the Wisp minus the value without it.
- **Horizon and terminal value.** Simulation ends at the end of the next stage. The terminal state (level, units and stars, gold, HP) is valued through an interface that "Board and lobby strength heuristic" fills in: `strength(board, level) → score` and `placement(own score, opponent scores, HP) → expected placement`. Death before the horizon maps to placement by the expected elimination order. The blend leans on HP for low-HP states until the evaluation harness tunes `terminal_hp_weight`.
- **Fights.** Each simulated combat round samples an opponent uniformly among those still alive. The outcome uses `win_probability(own score, opponent score, stage)`. Damage on a loss is the stage base plus `surviving_units(score gap, stage)`. Both functions belong to the same interface. Each opponent's strength starts from their last sighting and advances along a stage-keyed growth curve from tunables; with no opponent data, the lobby-average curve is used. Opponent eliminations within the horizon are not simulated.
- **Rules facts not yet verified** (whether PvE rounds keep a streak, PvE orb gold, Wisp shop parity) are flags and numbers in the per-patch static file with stated defaults: PvE leaves the streak unchanged, orb gold is an expected value per PvE round, and Wisp slots are 4.5 when unknown.
- **Advice.** The sub-engine states the current-round action: "Level now", "Roll to N gold", "Stop rolling, hold" or "Hold econ (50)". The Engine runs on every state change, and each roll is one, so a hit mid roll-down turns "Roll to 10" into "Stop rolling" at once. Mid-roll-down re-scoring simulates only the target comp, with fewer rollouts. The missed roll-down at 4-2 is this re-scoring at the floor: "keep rolling to 0" against "stop, roll at 5-1".
- **Line hysteresis.** Line choice is folded over the game history like the Game plan. The previously advised Line stays unless another beats it by the line margin (about 0.1 placement), so advice does not flip between rounds on noise.
- **Projection and pinned Line (Live mode only).** The econ advice carries a projection for each candidate Line, round by round to the horizon: gold, level, probability of having hit the key units, expected HP and expected placement. Surfaces draw it graphically. The player can pin a Line. The Engine then follows the pinned Line, as it follows a comp locked in the picker. When another Line passes the line margin, it notes "Line X beats your pin by 0.4 placement", but it never switches by itself. Post-game review shows pinned against recommended Lines. Free-form what-if editing of a Line is post-v1. Baseline mode can still draw the Guide's static, stage-keyed Line.
- **Cost, two tiers.** Every comp in the universe is screened analytically: closed-form hit odds under the comp's Guide Line, plus a rounds-left-to-live check against its main roll-down. Only the target comp, the Backup comp and the top M challengers from the screen (M about 2) are simulated; while the plan is Open, the top-k candidates are. The screen ranks challengers, and the simulation decides the pivot.
- **Comp fit terms.** This amends "Transition and pivot domain model". For simulated comps, the best Line's simulated expected placement is the backbone of comp fit: comp fit equals that value plus item fit plus augment fit. Terminal strength counts units, stars and level and holds items out, so item fit stays with the item sub-engine. Owned progress, hit probability and Line feasibility are inside the simulated result and are not added again. They survive as its reason decomposition. The hit term is the simulated placement minus the placement if every key unit arrives on time. The feasibility term is the share lost to deaths before the horizon. Example: "Ahri: 41 % to 2-star by 4-2 (−0.6), 18 % dead before 4-2 (−0.3)". Comps that are only screened keep the additive form from that ticket.
- **Tunables owned here:** `rollouts_full`, `rollouts_reroll`, `line_candidate_cap`, `gold_floors`, `all_in_rounds_left`, `stabilize_rounds_left`, `line_margin`, `default_lines_by_carry_cost`, `challengers_simulated`, `terminal_hp_weight` and `opponent_growth_curve`. The damage base by stage and the XP, gold, streak and interest tables live in the static file, taken from Riot data, together with the rules flags above.
- **Scenarios checked.**
  - A 3-2 roll-down at 40 HP: level 6, 34 gold, a weak board and a 3-loss streak give about 4 rounds left to live, so stabilize joins the candidates. The Guide's Line holds econ and reaches 4-2 near death, so it scores badly. The simulation weighs rolling now at level 6 against leveling to 7 and rolling, across floors. The expected call is "Level 7, roll to 10", re-scored after each roll until "Stop rolling" on a hit.
  - Fast 8 on a loss streak: a 5-loss streak at 3-2 with 60 HP and 48 gold. The candidates are the Guide's Line (8 at 4-2), 8 at 4-1, rolling at 5-1, and holding. Leveling early strengthens the board and risks the +2 or +3 streak gold. Path-dependent rollouts price that trade-off with no special rule.

Glossary terms Gold floor, Rounds left to live, Line margin, Stabilize and Pinned Line added to `CONTEXT.md`, and Line sharpened.

Input posted to "Board and lobby strength heuristic" (the interface), "Shop, Wisp and carousel decisions" (Wisp valuation through the simulator), "Probe live game data sources in a real TFT game" (rules facts to confirm), "Post-game review scope" (pinned Lines and projections) and "Transition and pivot domain model" (the comp fit amendment).

### 2026-10-04 — claude-code

Amendments from "Board and lobby strength heuristic", which defines the four interface functions:
- Terminal strength holds items generic, not out: a flat value per finished item and component, the same for every comp. The player's items are fixed across Lines and comps, so the term cancels in comp comparisons, and item fit stays with "Item decisions".
- `opponent_growth_curve` is computed from statistics (units by a standard level calendar × average unit-star power under shop odds, plus the stage-typical item term), not hand-typed. It is recomputed when statistics refresh.
- `win_probability` = σ(k_stage · power gap); `placement` = 1 + Σ P(opponent outlasts the player), using `terminal_hp_weight` on the HP gap in lost rounds; `surviving_units` = the winner's unit count × σ(c_stage · gap).

### 2026-10-04 — claude-code

Input from "Item decisions": this amends "the simulator holds the player's items fixed across Lines and comps". The item sub-engine values a slam (building a finished item now, or placing a single component on a unit) by running the current best Line twice with the same seed, once with the item built and once with the components held on the bench, as the Wisp valuation does. The simulator must therefore accept an item state as input and carry its generic item term in board power through the simulated rounds. At most 3 slam candidates are simulated per snapshot, which counts against the 100 ms budget.
