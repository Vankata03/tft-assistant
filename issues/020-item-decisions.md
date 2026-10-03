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

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": the item pressure signal is the item fit term this sub-engine contributes to comp fit through `fit(comp, state) → term`, a placement delta plus a reason template. Item fit assigns held finished items and components to a comp's item holders. A finished item of the wrong class (AD in an AP comp) is worth almost nothing, while components keep their full value. Taking a component, like any choice that could change the comp, is scored as the best comp fit across candidate comps after the choice. Item holders on the interim board, and how they hand items over during a transition, belong to this ticket; transition advice covers only which units are fielded, held and sold.
