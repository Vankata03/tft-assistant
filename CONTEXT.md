# TFT Assistant

A personal coach for Teamfight Tactics that reads the live game and advises the player on each round's decisions.

## Language

**Coach**:
The assistant as a whole: it reads game state and gives advice. It never acts in the game.
_Avoid_: Bot, AI player, helper

**Advice**:
A recommendation computed from the live game state for the current decision, such as "level now" or "hold this unit". Only Live mode gives advice.
_Avoid_: Callout (a callout is advice delivered by voice), tip

**Live mode**:
The opt-in mode in which the coach gives advice computed from the live game state, including what it knows of opponents' boards.
_Avoid_: Real-time mode, cheat mode

**Baseline mode**:
The mode in which the coach shows Guides, highlights and stage-keyed hints but never advice computed from the live game state.
_Avoid_: Compliant mode, safe mode

**Guide**:
Static content for one comp, fixed before the game: its econ and leveling plan, items, augments, positioning, interim board and pivot alternatives.
_Avoid_: Build, tier list

**Post-game review**:
A replay of a finished game's decisions against what the coach's engine would have chosen.
_Avoid_: Recap, match summary

**Replay record**:
What replaying one decision point of a game log through the engine yields: the player's choice, the engine's choice, every option the engine scored, the estimated cost and whether advice was shown. Post-game review and the evaluation harness both read replay records.
_Avoid_: Replay (alone), decision log

**Moment**:
A decision, or a run of the same decision over consecutive rounds, where the player's choice cost expected placement against the engine's choice. Post-game review surfaces the costliest moments.
_Avoid_: Mistake, error

**Close call**:
A decision where the player's choice and the engine's choice differ by less than the estimate's noise. It is never shown as a moment.

**Follow rate**:
The share of the advice shown in a game that the player followed.
_Avoid_: Compliance

**Evaluation harness**:
The tool that judges the engine's advice quality across many game logs and sets the engine's tunables against it. It reads the same replay records as post-game review but is not part of it.
_Avoid_: Test suite, benchmark

**Game log**:
The coach's record of one game: every snapshot of game state it read, every offer, roll, pick, sighting and fight result, and the keyframes taken at decision points. Post-game review replays it.
_Avoid_: Recording, replay file, match history (that is Riot's record)

**Keyframe**:
A screenshot kept in the game log at a decision point, such as a shop after a roll, an augment offer or a scouted board.
_Avoid_: Snapshot (a snapshot is the read game state, not an image)

**Sighting**:
What the coach learned of one opponent's board the last time the player scouted it, with its age in rounds. Confidence in a sighting fades as it ages.
_Avoid_: Scout (the player's action), opponent snapshot

**Purchase tracking**:
Knowing which units the player owns from what they bought, sold and were given, rather than from looking at the board.
_Avoid_: Shop tracking, inventory

**Engine**:
The deterministic part of the coach that computes what the coach would do from a game snapshot and the game's history. Live mode uses it during a game; post-game review uses it after a game in both modes.
_Avoid_: AI, model, solver

**Live advisor**:
The in-game loop that feeds live game state to the engine and shows its advice. It is the separable part of Live mode.
_Avoid_: Live engine, overlay

**Game plan**:
The player's current target comp together with its line, seeded from the comp's Guide and replaced by a pivot. An Open game plan keeps several candidate comps; a Committed one has one target comp and at most one backup comp.
_Avoid_: Strategy, plan (bare)

**Open**:
The early state of a game plan, before commitment: several candidate comps are kept and the strongest board is played while flexible units are held.
_Avoid_: Flex (as a noun)

**Committed**:
The state of a game plan after a commitment trigger, such as the first item completed for a carry, a 2-star key unit, a comp-defining augment, or a stage deadline. Leaving the target comp after this point is a pivot.

**Backup comp**:
The second-best comp in a committed game plan, whose key units are held when bench space allows so that a pivot is cheaper.
_Avoid_: Plan B, secondary comp

**Comp fit**:
The expected placement if the player plays a given comp from now on, given the units, items, augments, level, gold, HP and pool the player has. Game plan choices and pivots compare comps by comp fit.
_Avoid_: Comp score, tier

**Line**:
A sequence of level and roll-down timings through the game, such as "fast 8 at 4-2": the level to reach by each round, and the rounds in which to roll down, each down to a gold floor.
_Avoid_: Curve, leveling curve

**Gold floor**:
The gold a roll-down stops at if the key units have not been found, such as "roll to 10".
_Avoid_: Roll budget

**Rounds left to live**:
How many more lost rounds the player survives at the current HP, given the expected damage of a loss at the current stage.
_Avoid_: Lives, HP buffer

**Line margin**:
How much better another Line's expected placement must be than the currently advised Line's before the coach changes its Line advice.

**Stabilize**:
Spending now to field the strongest board the player can reach, regardless of the target comp, because few rounds are left to live.
_Avoid_: Panic roll

**Pinned Line**:
A Line the player chose in Live mode. The coach follows it and only notes when another Line beats it by the line margin.
_Avoid_: Locked Line, override

**Comp**:
The target team the player is building toward: units, carry, items and traits.
_Avoid_: Team, build, lineup

**Interim board**:
The units on the board before the comp is reached, kept for strength while collecting the comp.
_Avoid_: Early board, temp board

**Transition**:
Replacing the interim board with the comp's units while keeping board strength, ending when the comp is fielded.
_Avoid_: Swap, pivot

**Pivot**:
Abandoning the target comp for a different comp partway through the game, for example because its units are contested.
_Avoid_: Transition, switch

**Pivot margin**:
How much better another comp's comp fit must be than the target comp's before the coach calls a pivot. It is larger later in the game.

**Recommended board**:
The strongest set of units the player owns that fits on the board at the current level. Transition advice is the difference between it and the current board.
_Avoid_: Best board, optimal board

**Board power**:
A single number for how strong a board is in combat, on one scale for every stage, so any two boards can be compared directly. Placement and fight odds are derived from board power; they are not board power.
_Avoid_: Board score, board strength (as a number), rating

**Win chance**:
The probability that the player's board beats a given opponent's board in the next fight, derived from both boards' board power. Baseline mode shows it per opponent, as a number only.
_Avoid_: Win rate (a statistic of a comp or unit across many games), win odds

**Unguided comp**:
A comp that statistics sources know but that has no Guide. It is considered only when the player turns it on.

**Item holder**:
A unit in a comp that is meant to carry items, such as the carry or the main tank. A comp has at most three.
_Avoid_: Item carrier, itemizer

**Best-in-slot**:
The items a comp's Guide gives each item holder.
_Avoid_: BiS (in prose), ideal items

**Item fit**:
How much the player's finished items and components, given to a comp's item holders in the best way, change that comp's expected placement compared with the items its holders usually carry.
_Avoid_: Item score

**Augment fit**:
How much the augments the player holds change a comp's expected placement compared with the augments players of that comp usually take. An augment slot not yet picked counts as an average augment.
_Avoid_: Augment score, augment tier

**Comp-defining augment**:
An augment whose pick leaves one candidate comp clearly ahead of the others, mostly because of that augment's augment fit. Picking one commits the game plan.
_Avoid_: Carry augment, trait augment (as a synonym)

**Slam**:
Building a finished item now, or placing a single component on a unit, instead of holding the components on the bench.
_Avoid_: Force, rush

**Contested**:
A unit or comp that other players in the same lobby are also collecting, which lowers the odds of finding its copies.

**Roll**:
Spending 2 gold to refresh the shop.
_Avoid_: Reroll (a reroll comp is a separate idea), refresh

**Roll-down**:
Spending a large share of gold on rolls in one round to find key units.
_Avoid_: All-in

**Econ**:
The player's gold management: interest, streaks, and when to spend versus save.

**Wisp**:
Set 18's set mechanic: a one-shot effect (gold, XP, rerolls, units, items or a combat buff) sold for gold in the rightmost slot of every other shop, at most one per round. "Buy Wisp" is the recurring decision of whether its effect is worth its gold against the econ, level and roll plan.
_Avoid_: Charm (the Set 12 predecessor)

**Pre-coach baseline**:
The owner's average placement over the last 50 ranked games played without the coach, in the same set as the Live-mode games it is compared against. It is refreshed just before the first Live-mode game.
_Avoid_: Baseline (alone, it collides with Baseline mode), control group

**Key unit**:
A unit whose copies a comp needs at a target star level, such as its carry and core units. The target star level is usually 2, and 3 for a reroll comp's carry.
_Avoid_: Core unit (as a separate term), main unit

**Opener**:
The decisions from stage 1 to early stage 2 (the first carousel, early shop buys and items from the opening encounter) that seed the first candidate comps of an Open game plan.
_Avoid_: Early game, start
