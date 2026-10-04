---
id: 30
title: "Opponent model from trait-only sightings"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

How does the Engine model opponents when a sighting gives only the scouted player's traits?

"Benchmark open-source board recognition on probe frames" settled that scouted boards give traits only in v1: the board reader does not read opponent units, star levels, items or hexes. Every player's HP still comes from the HUD. Several earlier resolutions assume a sighting gives units and star levels:

- "Board and lobby strength heuristic" computes an opponent's board power from the sighting, imputing only what is missing (unseen items, empty slots below the opponent's level). With traits only, every unit is unseen.
- The same ticket's comp classifier labels opponents by unit overlap with each comp's final units. The contested count in "Transition and pivot domain model" uses those labels and the number of opponents holding 2 or more copies of a carry.
- "Econ, level and roll Line simulation" removes copies seen on opponents' boards from the pool for hit odds, and starts each simulated opponent from their last sighting.
- Win chance per opponent (second screen, and Baseline mode per "Board and lobby strength heuristic") is `win_probability` against the sighting's board power.

Decide, for each of these, what a trait-only sighting contributes: for example board power estimated from active trait breakpoints and the opponent's level, comp labels inferred from trait combinations, a contested term from traits, or a fallback to the growth curve with no contested term and no pool reduction. Decide what confidence each carries. The decision to read traits only in v1 stands; reopening opponent unit reading is out of this ticket.

Raised by "Assemble the MVP spec" as a gap between settled tickets. On resolution, update the spec's open items in `docs/spec.md` and the affected sections in `docs/spec/`.
