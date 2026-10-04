---
id: 9
title: "Game-state capture route"
labels: [wayfinder:grilling]
status: open
assignee:
parent: 1
blocked_by: [2, 3, 13]
---

## Question

Which automatic capture route (or combination) does the coach use, given the field coverage, reliability and policy findings? Decide what happens when a required field is unavailable from the chosen route, since manual entry is ruled out.

## Comments

### 2026-10-04 — claude-code

Input from "Policy stance and feature modes": Live mode may use every field the chosen route exposes, including Overwolf's augment keys and opponent-board keys (`board.opponent_board_pieces`, `match_stats.board_players`). Baseline mode needs augment names during selection for its statistics table, and the stage, shop and own board for Guide steps and shop highlighting. Policy therefore does not rule out any field; route choice can rest on coverage and reliability.

### 2026-10-04 — claude-code

Input from "Advice engine architecture": the Engine runs on the CPU only, with a budget of 100 ms per snapshot, so the GPU is shared only between the game and a vision model if screen capture is chosen. Each sub-engine declares its required fields and stays silent when the route lacks one, so a route gap disables specific advice rather than the coach. "Positioning decisions" is blocked on this ticket because live positioning depends on which opponent boards the route reveals.

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": contest is counted from each opponent's latest board sighting, plus benches only if the route exposes them. A sighting has full weight for about 2 rounds, then fades and lowers confidence; with no opponent data there is no contested term. The owner accepts scouting every opponent's board each round if a screen-capture route reads scouted boards reliably.

### 2026-10-04 — claude-code

Input from "Board and lobby strength heuristic": the error metrics for board power need, per combat round, the opponent fought, the result, and the player's HP lost. Scouted boards should record items and star levels when visible, because missing fields are imputed at the stage average and lower advice confidence. A route that logs these lets `win_probability` and `surviving_units` be calibrated from fight logs.

### 2026-10-04 — claude-code

Input from "Item decisions": the item sub-engine requires the items on the player's units and the item bench, and stays silent without the item bench. It also reads item offers (anvils, Item-category Wisps) and held removers and Reforgers when the route exposes them. Opponents' items are not used by this sub-engine.

### 2026-10-04 — claude-code

Input from "Augment decisions": the augment sub-engine requires the three offered augment ids, the offer tier, which options still have a reroll, and the augments the player holds. Advice must show within about 2 s of the offer appearing (the selection timer is about 43 s, then 58 s). The Riot match API no longer records augments for Set 18, so capture is the only source of held augments, and the coach's game log must record every offer, reroll and pick for post-game review.

### 2026-10-04 — claude-code

Input from "Shop, Wisp and carousel decisions": the shop and Wisp sub-engines require the shop's champion slots, the offered Wisp's id and cost, gold, board and bench, and the shop's slot count (5, or 4 with a Wisp) on every roll. The carousel sub-engine requires each carousel option's unit and item before the player's pick. A sub-engine whose fields are missing emits nothing.
