---
id: 22
title: "Positioning decisions"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: [9, 24]
---

## Question

How does the positioning sub-engine adjust the Guide's static positioning during a game? Live adjustments depend on what the capture route reveals about opponents' boards. Decide which adjustments v1 makes (for example carry corner against assassins, spreading against area damage, the next opponent's threats), which opponent data each needs, and what it advises when only scouted boards are available.

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": the recommended board decides which units are fielded each planning phase; this sub-engine decides where they stand.

### 2026-10-04 — claude-code

Input from "Game-state capture route": the route is screen capture only, with no Overwolf, so opponent boards are known only from the player's own scouting, each with a sighting age. If "Benchmark open-source board recognition on probe frames" passes, a scouted board gives units, hex positions, star levels and items; otherwise it gives the scouted player's traits only, and live positioning has no opponent positions to react to. The own board's hex positions come from the vision model; purchase tracking alone does not know them. The next opponent is not known before combat from capture, apart from what the player scouts.
