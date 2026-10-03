---
id: 12
title: "Transition and pivot domain model"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: [3, 5, 6]
---

## Question

How does the coach model a transition (interim board to final comp) and a pivot (abandoning the target comp for another)? Define the inputs each needs (own board, items, augments, gold, HP, contested units, opponents' boards, pool state), the triggers that start one, and the concrete advice it gives. Stress-test against scenarios such as a contested carry at 3-2 or a highroll that makes the interim board the final one.

## Comments

### 2026-10-04 — claude-code

Input from "Data source strategy": each Guide's static interim board comes from TFT Academy's `earlyComp` (units and items, no positions), positioned with MetaTFT's cell histogram. No source has early-board statistics, because the Riot API records only final boards. A dynamic interim board built from the units the player owns (Live mode, stages 2-1 to 3-2) must therefore be scored heuristically from static data: trait breakpoints, unit cost, star level and item fit, steered toward the Guide's target comp. This ticket owns that selection logic.

### 2026-10-04 — claude-code

Input from "Advice engine architecture": this ticket owns the Engine's Game plan layer, meaning the target comp and its Line. Comp choice, transition and pivot all live in that layer, and a pivot is a change of Game plan. Sub-engines never change the Game plan; they raise pressure signals (carry contested, augment or items fit another comp) that this layer weighs. Define the pressure signal, since "Item decisions", "Augment decisions" and "Shop, Wisp and carousel decisions" wait on it. The Engine is a pure function of the snapshot and the game history, so contested units and pool depletion must be derived from history, not stored state.
