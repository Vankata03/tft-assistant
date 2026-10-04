---
id: 31
title: "Baseline mode and opponent sightings"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

May Baseline mode capture opponent sightings and show a win chance computed from them, and does any Engine function run in-game in Baseline mode?

Two settled tickets disagree:

- "Policy stance and feature modes" rules that anything about opponents' boards is Live mode only, because Riot bans tracking opponents' champions during play. The same ticket puts "a win-chance estimate" and the list of opponents already faced (names and results only) into Baseline mode's grey zone.
- "Board and lobby strength heuristic" defines Baseline mode's win chance as `win_probability` against each possible next opponent from their last sighting. "Advice surface UX" shows it per player-list row on the Baseline-mode overlay.
- "Advice engine architecture" says that in Baseline mode the Engine runs only after a game ends, yet the win chance above calls the Engine's board power functions in-game, and the Baseline-mode Wisp worth table is computed by the Engine offline.

Decide whether Baseline mode records and uses sightings, what its win chance is computed from if not, and how to state which Engine functions Baseline features may call during a game (the `live` package boundary from "Stack and runtime" stands either way).

Raised by "Assemble the MVP spec" as a contradiction between settled tickets. On resolution, update `docs/spec.md` (modes and open items) and `docs/spec/surfaces.md`.
