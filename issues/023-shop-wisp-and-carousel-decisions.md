---
id: 23
title: "Shop, Wisp and carousel decisions"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: [12]
---

## Question

How do the shop, Wisp and carousel sub-engines decide their calls? Shop: buy, sell or hold per slot against the Game plan, the interim board and econ. Wisp: whether its one-shot effect is worth its gold against the current Line. Carousel and opener: which unit or item to take, and how the opener feeds the Game plan's initial comp choice. Decide the scoring for each and which thresholds go into the per-patch tunables file.

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": while the plan is Open, the shop holds key units of the top-k candidate comps; once Committed, it holds the target comp's and the Backup comp's key units within a bench budget. Transition advice ("Swap X for Y", "Hold Y", "Sell X") comes from the recommended board, so shop buy and sell calls must agree with it. Carousel picks, opener choices and Champion or Polymorph Wisps are scored like every choice that could change the comp: by the best comp fit across candidate comps after the choice. The opener feeds the Open plan's candidates.

### 2026-10-04 — claude-code

Input from "Econ, level and roll Line simulation": a Wisp on offer with a gold, XP or roll effect is valued through the Line simulator: the simulated Line value with the Wisp bought minus the value without it, using the same seed. The simulator ignores Wisps not yet offered. It takes the shop's champion slot count (5, or 4 with a Wisp) from the capture route when known, and assumes 4.5 otherwise.

### 2026-10-04 — claude-code

Input from "Item decisions": carousel items, item anvils, Item-category Wisps, artifact picks and removers on offer are scored by the best comp fit across candidate comps after the choice, where the item part of comp fit is item fit: the best assignment of finished items and components to the comp's item holders, valued from MetaTFT per-unit item statistics, minus the holders' average item value. A component counts at its option value, which falls to about 0 by stage 5.

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: "Transition and pivot domain model", "Econ, level and roll Line simulation", "Board and lobby strength heuristic", "Item decisions", "Augment decisions", "Policy stance and feature modes" and "Current TFT set and its mechanics, including wisp".

- **Shop buys are analytic.** The shop sub-engine runs on every roll, so it never simulates. A champion slot is a buy when any of these holds: it is a copy of a key unit of the target comp or the Backup comp (of the top-k candidate comps while the plan is Open); it raises the recommended board's board power by at least `board_power_buy_min`; or it makes a pair or a 2-star of an owned unit. Key-unit progress already sits inside the simulated comp fit, so these calls agree with the Game plan without re-simulating.
- **The Line owns gold.** Outside a roll-down, the shop may spend only an allowance: the gold above the Line's planned end-of-round gold, usually the interest breakpoint. Copies of the target comp's key units are always allowed, because the simulator already assumes they are bought. Inside a roll-down, every key-unit copy is a buy, down to the Line's gold floor. This keeps "Hold econ (50)" and a buy call from contradicting each other.
- **Bench priority.** When the bench overflows, units are kept in this order: target key units (ranked by copies toward the next star level), Backup key units, pairs of recommended-board units, interim units holding items, then the rest. Overflow sells from the bottom. In a roll-down round, the sale value of units below Backup priority counts as roll gold, and the advice is "Sell X, roll". Selling to reach an interest breakpoint is advised only for units in the lowest tier. This defines the bench budget that transition's "Hold Y" uses.
- **Wisp effect kinds.** Riot's seven categories are display only. The per-patch static file encodes each Wisp's effect as one kind, and each kind has one valuation path:
  - Gold, XP, shop and roll modifiers, and Risky Wisps with known odds: a same-seed Line simulation pair, with and without the Wisp (settled in "Econ, level and roll Line simulation").
  - Combat buffs: a one-round board power bonus from the static file, valued by the same simulation pair through fight odds, streak and HP.
  - Unit grants, Polymorphs and duplicators: the choice rule (best comp fit across candidate comps after the choice), as an expected value over random targets. A Polymorph II targets the highest-star eligible unit, so it is deterministic.
  - Item grants: the item choice rule from "Item decisions".
  - Effects that cannot be modelled: no Live call; only the static worth table, at low confidence.
- **Wisp gold price.** Simulation-pair Wisps pay their cost inside the pair. For choice-rule Wisps, the gold cost is priced by one more same-seed pair: the current best Line with the gold reduced by the cost, run with `rollouts_reroll`. The Wisp is a buy when its value minus its gold price exceeds `wisp_buy_margin`. Gold is therefore worth more at low HP and before a roll-down, as everywhere else in the Engine.
- **One Wisp per round, greedy.** The first Wisp over the margin is a buy, even mid roll-down. The option value of a better Wisp later in the round is not modelled: the simulator already ignores Wisps not yet offered, and per-Wisp numbers are grade B. The margin is the guard. The per-round Wisp cap comes from the static file (Blossom 9 raises it to two).
- **Carousel.** Each option is a unit plus an item, scored by the choice rule: the unit as owned progress and board power, and the item through item fit, with a component at its option value. Players pick in HP order, so the advice is a ranked list, "Take X; else Y, Z", re-ranked as options disappear. Opponents' picks are not predicted. The Guide's carousel priority from TFT Academy breaks ties.
- **Opener.** There is no opener sub-engine. The opening encounter is a static-file effect: free rolls (Reroll Subscription) feed the Line simulator, and anvils and forges use the item choice rule. The 1-1 carousel uses the carousel rule. Early buys are shop calls. The Open plan's first top-k candidates are ranked by comp fit at 1-1, which at that point is mostly the MetaTFT average plus the item fit of the held components plus the encounter's effect.
- **Baseline mode.** The shop highlight of the chosen comp's units is unchanged from "Policy stance and feature modes". The static Wisp worth table is computed offline by the Engine once per patch: each Wisp at each of its offer stages runs the same simulation pair on a standard state (the Guide's Line, median HP, a stage-average board) and is labelled "worth it", "situational" or "skip". The owner override file wins. The carousel shows the chosen comp's Guide priority list. None of these reads the live game state.
- **Advice.** Live mode: "Buy X", "Sell X", "Sell X, roll", "Buy Wisp" or "Skip Wisp" with the value and gold price in the reason, and "Take X; else Y, Z" at the carousel. Post-game review replays shop, Wisp and carousel choices through the same rules.
- **Required fields.** Shop slots (champions, plus the Wisp's id and cost), gold, board and bench for the shop and Wisp sub-engines; the carousel's units and items for the carousel. A sub-engine whose fields are missing emits nothing.
- **Tunables owned here:** `board_power_buy_min`, `hold_priority`, `bench_budget` and `wisp_buy_margin`. The per-patch static file holds each Wisp's effect kind and values, combat-buff board power bonuses, the per-round Wisp cap, and the opening encounters' effects.
- **Scenarios checked.**
  - Animate Shop (8 gold) at 4-2 on a roll-down Line: the simulation pair values about 9 free rolls against 8 gold, so the Wisp is a buy.
  - Polymorph II at 3-1 with a 2-star 2-cost interim unit: the choice rule scores the resulting 3-cost. If it is a key unit of the target comp, comp fit rises and the Wisp is a buy; if not, only its board power counts against the gold price.
  - Barter during a transition that sells a 2-star 4-cost: the simulation pair values the extra gold now, so the Wisp is a buy and the sell advice follows it.

Glossary terms Opener and Key unit added to `CONTEXT.md`.

Input posted to "Econ, level and roll Line simulation", "Transition and pivot domain model", "Game-state capture route", "Probe live game data sources in a real TFT game" and "Post-game review scope".
