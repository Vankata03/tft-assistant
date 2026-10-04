---
id: 27
title: "Evaluation harness"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

How is the Engine's advice quality judged before and during the 50 Live-mode games, and how are its tunables set against that judgement? "Post-game review scope" settled that replaying a game log through the Engine produces a replay record per decision point, and that the evaluation harness is a separate consumer of those records, re-run over every game log whenever the engine or the tunables change.

Decide:

- What the replay records are compared against: actual outcomes (fights, damage, placement), high-elo decisions from any available source, or the Engine's own consistency across versions.
- Which metrics the harness reports and their pass thresholds. Board power's metrics are already settled in "Board and lobby strength heuristic": final-board ranking (Spearman correlation and placement MAE) now; Brier score, log-loss and calibration by stage of `win_probability`, and damage MAE per lost round, once game logs exist.
- How each tunable is tuned and how overfitting to the owner's few games is avoided. Tunables waiting on this: pivot margins, comp fit weights, the Line margin, the terminal HP weight, the opponent growth curve, the item tunables (class prior strength, component discount), the augment tunables (tier-to-delta map, comp-defining margin), the shop and Wisp tunables (board power buy minimum, Wisp buy margin) and `review_min_cost`.
- What data the harness can use before the coach's own game logs exist, and how it treats games with capture gaps.
