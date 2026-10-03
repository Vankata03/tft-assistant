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
