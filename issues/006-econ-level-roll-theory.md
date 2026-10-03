---
id: 6
title: "TFT econ, level and roll math and established theory"
labels: [wayfinder:research]
status: closed
assignee:
parent: 1
blocked_by: []
---

## Question

What are the current hard numbers and the established theory behind econ, leveling and rolling? Numbers: shop odds per level, unit pool sizes per cost, XP to level, interest and streak gold, round structure and PvE rounds, damage formula. Theory: standard leveling curves (for example level 4 at 2-1, 6 at 3-2, 8 at 4-2), fast-8 versus reroll lines, roll-down timing, HP-based decisions, and how strong players reason about board transitions and comp pivots. Prefer primary sources (patch notes, Riot data) for numbers and high-elo coaches (TFT Academy, pro players' guides) for theory. Note which parts are solvable by calculation, such as the odds of hitting a specific unit for a given gold.

## Comments

### 2026-10-04 — claude-code (resolution)

Findings: branch `research/econ-level-roll-theory`, file `research/econ-level-roll-theory.md`. Numbers are for patch 18.3 and are dated per patch.

**Hard numbers, from Riot patch notes and game data:**
- Shop odds at level 8: 15/20/32/30/3 %.
- Copies per unit by cost: 30/25/18/10/9.
- XP to the next level: 2, 2, 6, 10, 20, 36, 56, 68, 68. Patch 18.2 cut level 7 to 8 to 56 XP.
- Streak gold: +1 for 2–4 games, +2 at 5, +3 at 6 or more.
- Interest: 1 gold per 10 held, capped at 5. Base income: 5 per round.
- Buying XP: 4 gold for 4 XP.
- Player damage: a stage base of 0/2/6/7/10/12/17/150, plus 1 per surviving enemy unit.
- Wisps alternate 5 and 4 buyable units per shop, which costs roughly 10 % of the hit rate during a roll-down.

**Heuristics:**
- Standard 4-cost line: level 4 at 2-1, 5 at 2-5, 6 at 3-2, 7 at 4-1, then 8 at 4-2 (fast 8) or 5-1.
- Reroll lines roll from 3-1 to 4-1, depending on the carry's cost.
- Roll depth depends on HP.
- Pivots follow items, contested units, upgrades and gold.

**What can be calculated directly:**
- Hit odds, as a Markov chain over shops.
- The XP and gold calendar.
- Interest loss.
- Damage taken and rounds left to live.
- Level-versus-roll comparisons.

Board strength against the lobby, and when to pivot, need statistics or a strength model.

Several low-grade "Set 18" guides still show stale numbers. The coach must take its numbers only from Riot notes and game data.

Open questions carried forward: systems changes in 18.4 and 18.5; Wisp effects on the pool; early-round income; whether PvE rounds keep a streak alive. TFT Academy's paywalled theory was not readable.
