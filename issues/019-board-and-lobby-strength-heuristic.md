---
id: 19
title: "Board and lobby strength heuristic"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

How does the Engine score a board's strength and the player's position in the lobby without a trained model? "Advice engine architecture" fixed the approach: match the board to the closest MetaTFT comp, start from its average placement, and adjust for completeness (units against level, star levels, finished items); lobby position ranks the player's score against opponents' scores in Live mode, with HP as the fallback. Decide the matching rule for boards that fit no comp, the completeness adjustments and their weights, how scouted or partial opponent data is handled, and how the win-chance estimate shown in Baseline mode relates to this score. This is the Engine's weakest part, so also decide how its error will be measured against recorded games.
