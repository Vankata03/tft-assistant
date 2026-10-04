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
