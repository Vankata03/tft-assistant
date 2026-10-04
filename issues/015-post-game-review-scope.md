---
id: 15
title: "Post-game review scope"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: [9, 11]
---

## Question

What does the post-game review show after a finished game, and what data does it need? Decide which decisions it replays against the engine (every round, or only key moments such as roll-downs, pivots and augment picks), how it presents the gap between the player's choice and the engine's, and where its data comes from: the coach's own capture log of the game, the Riot match API (personal key), or both. Decide whether the review doubles as the evaluation harness for advice quality, which is still in the map's fog.

## Comments

### 2026-10-04 — claude-code

Input from "Data source strategy": the coach logs every captured game from day one, and the owner will hold a Riot personal API key (see "Register a Riot personal API key"), usable only for the owner's own matches. Both data sources named in the question are therefore available.

### 2026-10-04 — claude-code

Input from "Advice engine architecture": the Engine is a pure function of the game snapshot, the game history and the data snapshot, so post-game review replays the captured game log through it round by round and gets the same advice Live mode would have given. Review prose comes from templates; v1 uses no language model. The Engine core runs post-game in both modes. Board and lobby strength is the Engine's weakest part, so if the review doubles as the evaluation harness it should measure that first (see "Board and lobby strength heuristic").

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": the Game plan is folded from the game history, so replaying the log reproduces every plan change. The review should show pivot calls the player ignored and pivots the player made without a call.

### 2026-10-04 — claude-code

Input from "Econ, level and roll Line simulation": in Live mode the player can pin a Line, and the Engine then follows the pin and only notes when another Line beats it by the line margin. The review should show pinned against recommended Lines, and each round's Line projection (gold, level, probability of having hit the key units, expected HP and expected placement) is available for replay. Free-form what-if editing of a Line was left for after v1, and the review is the natural place for it, because time is free there.
