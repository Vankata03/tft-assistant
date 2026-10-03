---
id: 18
title: "Econ, level and roll Line simulation"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

How does the econ, level and roll sub-engine choose between candidate Lines? "Advice engine architecture" fixed the method: simulate a few candidate Lines (the Guide's Line, one level earlier or later, roll-down now versus next stage) to the end of the next stage over the XP and gold calendar, hit odds and the damage model, scored by expected placement. Decide which candidates are generated and when, how hit odds account for contested units and Wisp shops, how HP and rounds left to live set roll depth, how a simulated outcome converts to expected placement, and which thresholds go into the per-patch tunables file. Stress-test against a 3-2 roll-down at 40 HP and a fast-8 Line on a loss streak.
