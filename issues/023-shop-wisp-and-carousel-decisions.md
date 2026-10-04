---
id: 23
title: "Shop, Wisp and carousel decisions"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: [12]
---

## Question

How do the shop, Wisp and carousel sub-engines decide their calls? Shop: buy, sell or hold per slot against the Game plan, the interim board and econ. Wisp: whether its one-shot effect is worth its gold against the current Line. Carousel and opener: which unit or item to take, and how the opener feeds the Game plan's initial comp choice. Decide the scoring for each and which thresholds go into the per-patch tunables file.

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": while the plan is Open, the shop holds key units of the top-k candidate comps; once Committed, it holds the target comp's and the Backup comp's key units within a bench budget. Transition advice ("Swap X for Y", "Hold Y", "Sell X") comes from the recommended board, so shop buy and sell calls must agree with it. Carousel picks, opener choices and Champion or Polymorph Wisps are scored like every choice that could change the comp: by the best comp fit across candidate comps after the choice. The opener feeds the Open plan's candidates.

### 2026-10-04 — claude-code

Input from "Econ, level and roll Line simulation": a Wisp on offer with a gold, XP or roll effect is valued through the Line simulator: the simulated Line value with the Wisp bought minus the value without it, using the same seed. The simulator ignores Wisps not yet offered. It takes the shop's champion slot count (5, or 4 with a Wisp) from the capture route when known, and assumes 4.5 otherwise.
