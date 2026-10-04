# Sub-engines

Part of the [MVP spec](../spec.md). The Engine's contract, Game plan, comp fit and board power are in [engine.md](engine.md). Tunable names below are indexed in [tunables.md](tunables.md).

Each sub-engine reads the Game plan and the snapshot, emits advice for its decision, contributes its comp fit term through `fit(comp, state)`, and stays silent when a required field is missing ([capture.md](capture.md#missing-stale-and-conflicting-fields)). Post-game review replays every sub-engine through the same rules.

## Econ, level and roll

Sources: [TFT econ, level and roll math and established theory](../../issues/006-econ-level-roll-theory.md), [Econ, level and roll Line simulation](../../issues/018-econ-level-roll-line-simulation.md), [Board and lobby strength heuristic](../../issues/019-board-and-lobby-strength-heuristic.md), [Shop, Wisp and carousel decisions](../../issues/023-shop-wisp-and-carousel-decisions.md), [Item decisions](../../issues/020-item-decisions.md), [Augment decisions](../../issues/021-augment-decisions.md).

### Method

Seeded Monte Carlo with common random numbers. Each candidate Line runs N rollouts to the end of the next stage, and every Line sees the same random shops and fights, so noise cancels when Lines are compared. Monte Carlo keeps the variance that decides death at low HP. The closed-form shop Markov chain stays as a cheap helper for screening and for reason text such as "62 % to hit".

### Lines

A Line is a schedule over the remaining rounds: a level target per round, and a set of roll-down rounds, each with a gold floor. Outside a roll-down, econ holds interest and buys XP only to meet the level targets.

Candidates are regenerated every planning phase, deduplicated and capped at about 7 (`line_candidate_cap`):

1. The Guide's Line (for an unguided comp, the default Line for its carry's cost).
2. The next level step one stage-round earlier.
3. The next level step one stage-round later.
4. Roll-down now, at the current level.
5. Roll-down at the next Line point.
6. Hold: econ to 50, level only.
7. Stabilize, only when rounds left to live fall below `stabilize_rounds_left`: roll now to the floor that buys the strongest board, ignoring the target comp's key units.

### Simulation rules

- **Roll depth is emergent.** Roll-down candidates carry several gold floors (`gold_floors`: 50, 30, 10, 0) and the simulation picks the best. Low HP raises the cost of losses and death, so deeper floors win without an HP-to-floor table. Below `all_in_rounds_left`, floor 0 is always a candidate.
- **No deliberate loss streak.** The coach never advises playing to lose. Streak is the outcome of playing the recommended board, and path-dependent rollouts price the streak gold a stronger board gives up.
- **Hit odds.** The pool loses only the expected copies on opponents' inferred boards ([engine.md](engine.md#contested)), with sightings fading after about 2 rounds. Opponents' future buys are not projected. The shop's champion slot count (5, or 4 with a Wisp) comes from capture when known; otherwise 4.5 is assumed. Wisps not yet offered are ignored.
- **Fights.** Each simulated combat round samples an opponent uniformly among those alive. The outcome uses `win_probability`; damage on a loss is the stage base plus `surviving_units`. Each opponent starts from their last sighting's board power ([engine.md](engine.md#opponent-model)) and advances along the opponent growth curve; with no opponent data, the lobby-average curve is used. Opponent eliminations within the horizon are not simulated.
- **Terminal value.** The simulation ends at the end of the next stage. The terminal state (level, units and stars, generic items, gold, HP) is valued with `strength` and `placement`. Death before the horizon maps to placement by the expected elimination order. `terminal_hp_weight` sets how much the HP gap counts.
- **Rules facts with defaults** in the static file: PvE leaves the streak unchanged (confirmed by the probe game), PvE orb gold is an expected value per PvE round (not yet confirmed), and Wisp slots are 4.5 when unknown.
- **Inputs for same-seed pairs.** The simulator accepts an item state, a one-round board power bonus, a gold reduction alone, and Wisp-style effects (gold, XP, rolls). Other sub-engines value a choice as the best Line's simulated value with the choice minus without it, using the same seed.

### Advice

- Current-round actions: "Level now", "Roll to N gold", "Stop rolling, hold" and "Hold econ (50)".
- Each roll is a state change, so a hit mid roll-down turns "Roll to 10" into "Stop rolling" at once. Mid-roll-down re-scoring simulates only the target comp, with fewer rollouts (`rollouts_reroll`). The missed roll-down at 4-2 is this re-scoring at the floor: "keep rolling to 0" against "stop, roll at 5-1".
- **Line hysteresis.** Line choice is folded over the history like the Game plan. The advised Line stays unless another beats it by `line_margin` (about 0.1 placement).
- **Projection.** In Live mode the advice carries a round-by-round projection for each candidate Line: gold, level, probability of having hit the key units, expected HP and expected placement.
- **Pinned Line.** In Live mode the player can pin a Line. The Engine follows it, as it follows a comp locked in the picker, and notes "Line X beats your pin by 0.4 placement" when another Line passes the margin. It never switches by itself.
- **Baseline mode** draws the Guide's static, stage-keyed Line.

### Cost

Every comp in the universe is screened analytically: closed-form hit odds under its Guide Line, plus a rounds-left-to-live check against its main roll-down. Only the target comp, the Backup comp and the top `challengers_simulated` (about 2) from the screen are simulated; while the plan is Open, the top-k candidates are. The screen ranks challengers; the simulation decides a pivot.

### Scenarios checked

- **3-2 roll-down at 40 HP.** Level 6, 34 gold, a weak board and a 3-loss streak give about 4 rounds left to live, so stabilize joins the candidates. The Guide's Line holds econ and reaches 4-2 near death, so it scores badly. Expected call: "Level 7, roll to 10", re-scored after each roll until "Stop rolling" on a hit.
- **Fast 8 on a loss streak.** A 5-loss streak at 3-2 with 60 HP and 48 gold. Candidates: the Guide's Line (8 at 4-2), 8 at 4-1, rolling at 5-1, and holding. Rollouts price the trade between a stronger board and streak gold with no special rule.

## Items

Sources: [Item decisions](../../issues/020-item-decisions.md), [Probe live game data sources in a real TFT game](../../issues/013-probe-live-game-data.md).

**Item rules (confirmed by the probe game).** A finished item stays on its unit until the unit is sold (its items return to the item bench) or an Item Remover takes it off. A single component sits on a unit and gives its stats; a second component combines in place.

- **Item value.** The value of item X on unit Y comes from MetaTFT's per-unit item statistics (`unit_items_processed`): the unit's average placement with the item minus its average placement overall. Thin samples shrink toward a class prior (AD, AP, tank, utility), weighted by sample size; the class prior makes a wrong-class finished item worth almost nothing. A holder's items add up; 3-item builds are not modelled. Emblems, artifacts, Radiant and support items are valued the same way; kinds with no statistics fall back to the class prior with lowered confidence.
- **Item holders.** Each comp has at most 3: the units that carry items in the Guide's `finalComp`, or for an unguided comp the 2 or 3 units with the highest item frequency in its MetaTFT cluster. The owner override wins. The Guide's best-in-slot items pick the holders and break ties.
- **Item fit** (this sub-engine's comp fit term) is the value of the best assignment of the player's finished items and components to the comp's holders, minus the frequency-weighted average value of the items those holders usually carry. A typical set scores about 0, best-in-slot above 0, wrong-class items below 0.
- **Components** count at option value: the expected value of the best item each can still finish, given the other held components and the expected future components by stage (`component_income_by_stage`), discounted toward about 0 by stage 5 (`component_discount_by_stage`). Assignment is an exhaustive search; with about 10 components, 3 holders and the recipe table it is small.
- **Slam versus hold.** Building a finished item now, or placing a single component on a unit, is valued by a same-seed Line simulation pair (item built against components held). The difference is the tempo value: HP saved, streak kept. The sub-engine adds the change in item fit and calls the slam if the sum is positive. At most `slam_candidate_cap` (3) slams are simulated per snapshot.
- **Interim holders.** A finished item goes on its comp holder if that unit is owned and fielded. Otherwise it goes on an interim unit chosen for the most board power now and the right item class. Without a remover in hand, an interim holder must be a unit the comp will sell; an item is never locked on a comp unit that is not its holder. With k removers held, up to k units that stay on the board may hold items when that gives more board power.
- **Handover.** When the recommended board drops an interim holder, transition advice carries its items: "Sell X, items to Y". When holder Y is fielded and the unit carrying its items stays, the advice is "Use remover on X, items to Y", if the move raises item fit plus board power. Removers are spent greedily.
- **Open plans.** While Open, items are allocated to maximize item fit across the top-k candidates, weighted by a softmax of comp fit (`open_candidate_temperature`). A finished item on a carry is a commitment trigger, so the weighting keeps a slam from committing to a weak candidate. Items on interim holders that will be sold do not commit the plan.
- **Choices and tools.** Item anvils, Item-category Wisps, artifact picks and removers on offer are scored by the choice rule (best comp fit across candidates after the choice). Reforger is advised only for a wrong-class finished item when reforging raises item fit.
- **Advice.** Live mode: "Build X on Y", "Place component on Y", "Hold components", "Sell X, items to Y", "Use remover on X, items to Y", "Reforge X" and "Take X", with item fit and tempo numbers in the reason. Baseline mode: the chosen comp's best-in-slot items and recipes, with held components that build them highlighted, and no slam calls.
- **Required fields.** Items on the player's units and the item bench. Opponents' items are not used.

## Augments

Sources: [Augment decisions](../../issues/021-augment-decisions.md), [Probe live game data sources in a real TFT game](../../issues/013-probe-live-game-data.md).

**Augment rules (confirmed by the probe game).** Offers come at 2-1, 3-2 and 4-2. All three options in an offer share a tier (silver, gold or prismatic), shown by the icon colour. Each option has its own reroll, usable once and free. The selection timer opened at about 48 to 49 s for all three offers.

- **Augment value** of augment A for comp C is a placement delta from a chain. While no statistics exist: the per-comp MetaTFT tier, else the global MetaTFT tier, converted through `augment_tier_delta` (starting at MetaTFT's own map: S −0.3, A −0.15, B 0, C +0.15, D +0.3). An augment absent from the comp's list uses its global tier with lowered confidence.
- **When statistics return** for an augment past about 500 boards: comp C's average placement with A minus comp C's average, shrunk toward the global delta by sample size (`augment_prior_strength`), with a thin global delta shrunk toward a tier prior. Per-pick-stage statistics are used when available. A stale or changed-this-patch flag multiplies the prior strength (`augment_flag_prior_multiplier`) and lowers confidence; a flagged augment is never excluded.
- **Augment fit** (this sub-engine's comp fit term) is the sum of the held augments' values for that comp. Unpicked slots count 0, as an average augment. Pairs and trios are not modelled.
- **Econ augments**, tagged in the static file (gold, XP or free rolls, encoded like Wisp effects), are valued by a same-seed Line simulation pair instead of the tier, which makes them depend on HP, Line and stage.
- **Augments that grant items, units, emblems or traits** use the tier or statistics value only, to avoid counting their average effect twice.
- **Ranking an offer.** Each option is scored by the best comp fit across candidate comps after taking it.
- **Rerolls.** Reroll every option except the current best, then re-rank. Reroll the best option only if the expected best value after the reroll beats keeping it. The expectation runs over the tier's pool minus the options shown, with uniform weights.
- **Comp-defining augment.** A pick commits the Game plan when, after it, the top candidate's fit leads the second by at least `comp_defining_margin` and augment fit accounts for most of that lead. There is no hand-tagged list.
- **Confidence and ties.** Tier-based advice is capped at medium confidence. A tier list whose `updated` date is before the current patch date is flagged stale. When options share a tier and no simulated delta separates them, the advice says "close", shows both, and breaks the tie by the Guide tag, then the global tier. Once statistics return, options inside each other's 95 % margin show as "close". A new augment with no data uses the tier prior plus the Guide tag.
- **Advice.** Live mode: "Take X" and "Reroll options 1 and 3", with the value source in the reason (for example "X: S-tier for this comp (−0.3), Line simulation +0.2"), within about 2 s of the offer. Baseline mode: per-comp and global tiers with the Guide tag; it switches to an average-placement table if statistics return.
- **Required fields.** The three offered augment ids, the offer tier, which options still have a reroll, and the augments held. Without the offer the sub-engine emits nothing. Without held augments, augment fit is 0 for every comp.

## Shop

Sources: [Shop, Wisp and carousel decisions](../../issues/023-shop-wisp-and-carousel-decisions.md), [Transition and pivot domain model](../../issues/012-transition-and-pivot-model.md).

- **Analytic, never simulated.** The shop runs on every roll. A champion slot is a buy when any of these holds:
  - it is a copy of a key unit of the target comp or the Backup comp (of the top-k candidates while Open);
  - it raises the recommended board's board power by at least `board_power_buy_min`;
  - it makes a pair or a 2-star of an owned unit.
- **The Line owns gold.** Outside a roll-down the shop may spend only the gold above the Line's planned end-of-round gold, usually the interest breakpoint. Copies of the target comp's key units are always allowed, because the simulator assumes they are bought. Inside a roll-down, every key-unit copy is a buy, down to the Line's gold floor.
- **Bench priority** (`hold_priority`). When the bench overflows, units are kept in this order: target key units (by copies toward the next star level), Backup key units, pairs of recommended-board units, interim units holding items, then the rest. Overflow sells from the bottom. In a roll-down round, the sale value of units below Backup priority counts as roll gold ("Sell X, roll"). Selling to reach an interest breakpoint is advised only for units in the lowest tier. This is the bench budget behind transition's "Hold Y".
- **Advice.** "Buy X", "Sell X" and "Sell X, roll". Baseline mode: a display-only highlight of the chosen comp's units.
- **Required fields.** Shop slots, gold, board and bench.

## Wisp

Sources: [Current TFT set and its mechanics, including wisp](../../issues/005-current-set-mechanics.md), [Shop, Wisp and carousel decisions](../../issues/023-shop-wisp-and-carousel-decisions.md), [Probe live game data sources in a real TFT game](../../issues/013-probe-live-game-data.md), [Patch-day and new-set workflow](../../issues/028-patch-day-and-new-set-workflow.md).

The Wisp is Set 18's set mechanic and is built as a per-set plug-in behind the `fit(comp, state)` and same-seed pair interface ([patch-workflow.md](patch-workflow.md#new-set)).

**Wisp rules (confirmed by the probe game).** A Wisp is sold in the rightmost slot of every other shop, and rerolls count as shops. A player can buy one per round. A Wisp is offered only at a price the player can afford when the shop appears. A shop showing a Wisp shows four champions; after a Wisp is bought, its slot refills with a champion. The 16 Wisps seen cost 0 to 4 gold.

- **Effect kinds.** Riot's seven categories are display only. The static file encodes each Wisp's effect as one kind, and each kind has one valuation path:
  - gold, XP, shop and roll modifiers, and Risky Wisps with known odds: a same-seed Line simulation pair, with and without the Wisp;
  - combat buffs: a one-round board power bonus from the static file, valued by the same pair through fight odds, streak and HP;
  - unit grants, Polymorphs and duplicators: the choice rule, as an expected value over random targets (a Polymorph II targets the highest-star eligible unit, so it is deterministic);
  - item grants: the item choice rule;
  - effects that cannot be modelled: no Live call, only the static worth table at low confidence.
- **Gold price.** Simulation-pair Wisps pay their cost inside the pair. For choice-rule Wisps, one more same-seed pair prices the gold: the best Line with gold reduced by the cost, run with `rollouts_reroll`. A Wisp is a buy when its value minus its gold price exceeds `wisp_buy_margin`.
- **Greedy.** The first Wisp over the margin in a round is a buy, even mid roll-down. The per-round cap comes from the static file (Blossom 9 raises it to two).
- **Advice.** "Buy Wisp" or "Skip Wisp", with value and gold price in the reason.
- **Baseline mode.** A static Wisp worth table, computed offline by the Engine once per patch: each Wisp at each of its offer stages runs the same pair on a standard state (the Guide's Line, median HP, a stage-average board) and is labelled "worth it", "situational" or "skip". The owner override wins.
- **Scenarios checked.** Animate Shop (8 gold) at 4-2 on a roll-down Line is a buy (about 9 free rolls against 8 gold). Polymorph II at 3-1 on a 2-star 2-cost is a buy if the resulting 3-cost is a target key unit; otherwise only its board power counts against the price. Barter during a transition that sells a 2-star 4-cost is a buy, and the sell advice follows it.
- **Required fields.** The offered Wisp's id and cost, gold, board, bench and the shop's slot count.

## Carousel and opener

Sources: [Shop, Wisp and carousel decisions](../../issues/023-shop-wisp-and-carousel-decisions.md), [Probe live game data sources in a real TFT game](../../issues/013-probe-live-game-data.md).

- **Carousel.** Shared carousels came at 2-4, 3-4, 4-4 and 5-4 in the probe game, plus the 1-1 carousel. Each option is a unit plus an item, scored by the choice rule: the unit as owned progress and board power, the item through item fit (a component at its option value). Players pick in HP order, so the advice is a ranked list, "Take X; else Y, Z", re-ranked as options disappear. Opponents' picks are not predicted. The Guide's carousel priority breaks ties. Baseline mode shows the Guide's priority list.
- **Opener.** There is no opener sub-engine. The opening encounter is a static-file effect: free rolls (Reroll Subscription) feed the Line simulator, and anvils and forges use the item choice rule. The 1-1 carousel uses the carousel rule. Early buys are shop calls. The Open plan's first candidates come from comp fit at 1-1 ([engine.md](engine.md#state)).
- **Required fields.** Each carousel option's unit and item.

## Positioning

Sources: [Positioning decisions](../../issues/022-positioning-decisions.md), [Data source strategy](../../issues/010-data-source-strategy.md).

- **Rule-based, never scored.** Board power has no hex term, v1 has no combat simulator, and no source records position statistics. The sub-engine emits a target layout with a template reason. It adds no comp fit term, gets no placement delta and never enters the Line simulation.
- **Base layout.** The recommended board decides which units are fielded. Units the Guide places keep the Guide's hex (owner override first, then TFT Academy `boardIndex`). Every other unit is placed by one assignment that maximizes the summed log-frequency of MetaTFT's cell histogram over the free cells, so a filler unit cannot take a carry's usual cell.
- **Adjustments**, applied in this order. Each unit takes at most one, and owner-override hexes never move.
  1. Own positional mechanics: traits and augments with hex effects, such as Greenfather's seed hex buffs.
  2. Anti-dive: when likely opponents threaten the backline, the carry goes to a corner with a bodyguard tank, or to the side away from the threat.
  3. Anti-AoE spread: when likely opponents carry area damage, backliners not placed by anti-dive spread apart.
  4. Fill: every remaining unit takes its base-layout hex.

  Anti-dive and anti-AoE may move units the Guide placed.
- **Threat share.** Anti-dive and anti-AoE read the possible next opponents: the lobby minus recently met players. The threat share is the fraction of those opponents whose sighting carries the threat tag, each weighted by sighting confidence, which fades with age. An adjustment turns on at `threat_share_on` (about 0.5) and off below `threat_share_off` (about 0.3). Opponents never scouted are left out of the share. With no sightings, both adjustments stay off.
- **Threat tags** (`backline_access`, `aoe`) are derived by keyword rules over CommunityDragon's trait and ability text: for example leap, dash, jump, blink, "farthest" and "backline" for `backline_access`; "adjacent", "hexes around", "in a line", "cone" and "all enemies within" for `aoe`. A unit is tagged from its ability text. A trait is tagged from its own text, and also when most units that can activate it carry the tag, because a sighting gives traits only. A tag applies from the trait's lowest breakpoint unless the text ties it to a higher one. The owner override file has a threat-tag section that wins. Each refresh logs every tag with the phrase that matched and a diff against the previous patch.
- **Form and timing.** Advice is a target layout for the whole board. Units whose current hex the board reader knows get a move arrow; a unit known only to purchase tracking shows its target hex without one. The layout is issued once per planning phase after the board has settled (no unit change for about 2 s, `board_settle_seconds`) and re-issued only when the recommended board changes or an adjustment flips. Voice speaks only when anti-dive or anti-AoE turns on, for example "carry to corner, assassins likely".
- **Baseline mode** shows only the Guide's final and interim layouts.
- **Review.** Positioning is never a moment. The review shows a note per fight: whether a layout was advised and followed, and the result against win chance.
- **Out of v1.** Counter-positioning against an enemy carry's hex, and placement against Zephyr, Shroud or other position-mirroring items.
