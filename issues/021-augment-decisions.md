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
