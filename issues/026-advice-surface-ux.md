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
