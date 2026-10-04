---
id: 33
title: "Data refresh trigger and silent sessions"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

Two small gaps found while assembling the spec:

1. **Refresh trigger.** "Data source strategy" refreshes at app start and between games and pulls each source once it is past its own minimum age: 1 hour for statistics, 6 hours for Guides, and on patch change for static data. "Stack and runtime" runs the refresh at core start and on the lobby or end-of-game phase "if the data is older than 6 hours". Decide which rule governs, for example whether the 6-hour check applies to the whole data snapshot or only to Guides.
2. **Silent sessions.** "Evaluation harness" introduced silent games, which show nothing and keep their review closed until the Live-mode run starts. "Policy stance and feature modes" gives the owner's build one Live mode switch per session, off by default. Decide how the owner puts a session into silent mode (for example a three-way session mode: silent, Baseline, Live), how a silent game is flagged in the game log and the game index, and how the review lock is lifted when the Live-mode run starts.

Raised by "Assemble the MVP spec". On resolution, update `docs/spec/data.md`, `docs/spec/review-and-harness.md`, `docs/spec/runtime.md` and the spec's open items.
