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
The player's current target comp together with its line, seeded from the comp's Guide and replaced by a pivot.
_Avoid_: Strategy, plan (bare)

**Line**:
A sequence of level and roll-down timings through the game, such as "fast 8 at 4-2".
_Avoid_: Curve, leveling curve

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
