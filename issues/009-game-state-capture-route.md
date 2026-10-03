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
