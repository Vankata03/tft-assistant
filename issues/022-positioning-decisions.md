---
id: 22
title: "Positioning decisions"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: [9]
---

## Question

How does the positioning sub-engine adjust the Guide's static positioning during a game? Live adjustments depend on what the capture route reveals about opponents' boards. Decide which adjustments v1 makes (for example carry corner against assassins, spreading against area damage, the next opponent's threats), which opponent data each needs, and what it advises when only scouted boards are available.

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": the recommended board decides which units are fielded each planning phase; this sub-engine decides where they stand.
