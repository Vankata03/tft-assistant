---
id: 21
title: "Augment decisions"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: [12]
---

## Question

How does the augment sub-engine rank an augment offer in Live mode? Inputs are the Game plan, augment statistics (per comp if MetaTFT's `comp_augment_tiers` holds them, otherwise global), the current board and the stage. Decide how per-comp and global statistics combine, how rerolls are advised, how an augment that fits a different comp raises a pressure signal on the Game plan, and how flagged or stale statistics change the ranking.

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": the augment pressure signal is the augment fit term this sub-engine contributes to comp fit through `fit(comp, state) → term`. An augment offer is ranked by the best comp fit across candidate comps after taking each option (the top-k candidates while the plan is Open; the target comp, the Backup comp and other Guides once Committed). The sub-engine never changes the plan; if an augment makes another comp best, the Game plan layer pivots on its next check, through the pivot margin. Checked scenario: with full AD items, an AP augment raises AP comps' fit only slightly because their item fit is near zero, so it ranks low and no pivot follows. A comp-defining augment is a commitment trigger.
