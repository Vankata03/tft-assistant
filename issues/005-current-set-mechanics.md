---
id: 5
title: "Current TFT set and its mechanics, including wisp"
labels: [wayfinder:research]
status: closed
assignee:
parent: 1
blocked_by: []
---

## Question

Which TFT set and patch are live as of October 2026, and what are its set-specific mechanics? In particular: what is the "wisp" mechanic, what decision does it put to the player (when and whether to buy it, what it costs, what it gives), and how does it interact with econ, leveling and rolling? List every other set mechanic that changes the standard econ, roll or transition decisions, and where reliable mechanic details are published (patch notes, Community Dragon data).

## Comments

### 2026-10-04 — claude-code (resolution)

Findings: branch `research/current-set-mechanics`, file `research/current-set-mechanics.md`.

The live set is Set 18, Enchanted Wilds, on patch 18.3. Patch 18.4 is due 2026-10-07, and Set 19 starts around 2026-12-01. The Wisp is Set 18's headline mechanic. It is a one-shot effect sold in the rightmost shop slot of every other shop. A player can buy at most one per round, during the planning phase only. Costs run from about 0 to 10 gold, with late outliers. There are seven categories: Champion, Combat, Misc, Shop, Gold/XP, Risky and Item.

Wisps change the econ, level and roll decisions directly:
- Some XP Wisps are cheaper per XP than buying XP.
- Gold Wisps shift interest breakpoints.
- Shop Wisps change roll cost and odds.
- Champion and Polymorph Wisps can drive transitions.
- A shop showing a Wisp shows four champions, not five, which changes the roll-odds maths.

Traits that alter the shop or econ also matter: Blossom, Inferno, Riftbeast and Avatar. So do several gold and XP sources.

Data sources: Riot patch notes are authoritative for rules. Community Dragon has Wisp text and values but no costs or offer stages. SeeMeta has costs but is third-party (grade B-). Wisp tables change every patch, so the per-patch data refresh must cover them.

Open questions carried forward: whether "every other shop" counts rolls; shop behaviour after a Wisp is bought; conflicting values between sources; where Wisp costs live in game data.
