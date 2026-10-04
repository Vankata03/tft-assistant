---
id: 26
title: "Advice surface UX"
labels: [wayfinder:prototype]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

What does each surface (the in-game overlay, the second-screen window and voice callouts) show in each mode and game phase, and how does advice compete for the player's attention? The owner wants the coach graphical and interactive, not only text. In Live mode the econ advice carries a per-Line projection and lets the player pin a Line ("Econ, level and roll Line simulation"), so the surfaces need a way to show and pick Lines within a planning phase. Mode rules per surface are settled in "Policy stance and feature modes".

Decide, with a rough prototype to react to:

- What goes on the overlay versus the second screen versus voice, per game phase (planning, combat, augment selection, carousel).
- The latency budget per phase. Capture reads a change within about 250–500 ms ("Game-state capture route"), and augment advice must show within about 2 s of the offer.
- How each opponent's sighting age is shown, and whether the coach prompts the player to scout an opponent whose board is old.
- How low-confidence fields (stale reads, a board that purchase tracking and vision disagree on) show to the player.

## Comments

### 2026-10-04 — claude-code

Input from "Post-game review scope": the review opens on demand in the second-screen window after a "review ready" notification at game end, with no voice. Its content is settled; its layout belongs here. The top of the review holds placement, estimated cost per category, follow rate, a Game plan timeline, a Line chart (actual against recommended and pinned Lines) and a fight strip (win chance against result). Below it come the top 5 moments as cards (round, category, the player's choice, the Engine's choice, estimated cost, template reason, shown-advice status, keyframe), each expanding to the options the Engine scored; the full round timeline; and a debug tab. A cross-game list shows each game's placement, total estimated cost and worst category.

### 2026-10-04 — claude-code

Input from "Positioning decisions": positioning advice is a target layout for the whole board, issued once per planning phase after the board has settled for about 2 s, and re-issued only when the recommended board changes or an anti-dive or anti-AoE adjustment turns on or off. Units whose current hex is known get a move arrow; a unit known only to purchase tracking shows its target hex without one. Each adjustment carries a template reason. Voice speaks only when an anti-dive or anti-AoE adjustment turns on. Baseline mode shows only the Guide's own final and interim layouts.
