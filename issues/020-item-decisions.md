---
id: 20
title: "Item decisions"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: [12]
---

## Question

How does the item sub-engine decide component allocation and when to slam a finished item? It reads the Game plan's target comp and the Guide's best-in-slot items, and is greedy (no lookahead). Decide how components are assigned when the target comp's items cannot all be built, when slamming a non-best-in-slot item beats holding components (HP, streak, stage), how item holders on the interim board hand items to the carry during a transition, and when item fit raises a pressure signal for a pivot.
