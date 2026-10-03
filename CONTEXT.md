# TFT Assistant

A personal coach for Teamfight Tactics that reads the live game and advises the player on each round's decisions.

## Language

**Coach**:
The assistant as a whole: it reads game state and gives advice. It never acts in the game.
_Avoid_: Bot, AI player, helper

**Advice**:
A recommendation the coach gives the player for the current decision, such as "level now" or "hold this unit".
_Avoid_: Callout (a callout is advice delivered by voice), tip

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
