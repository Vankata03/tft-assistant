---
id: 16
title: "Record the pre-coach baseline"
labels: [wayfinder:task]
status: open
assignee:
parent: 1
blocked_by: [17]
---

## Question

What are the owner's current rank and average placement over 50 games played without the coach, on the main account? Decide first whether already-played Set 18 ranked games, pulled from the Riot match API with a development or personal key, count toward the 50, or whether only fresh games played from now on count. Then record the 50 placements, the average, and the rank at the start and end, so the 50 Live-mode games can be compared against them.

## Comments

### 2026-10-04 — claude-code

Blocked by "Register a Riot personal API key". "Data source strategy" chose a personal key, used only for the owner's own matches, over 24-hour development keys.

### 2026-10-04 — claude-code

Unblocked by "Register a Riot personal API key". A development key works now (stored at `$HOME\.config\tft-assistant\riot-api-key`, regenerated daily); the personal key is pending Riot's review. The owner's account (EUNE, region `europe`) has at least 100 matches in `tft-match-v1`, across all queues, so past games must be filtered to ranked and Set 18 from the match details. `tft-league-v1` by PUUID gives tier, rank and LP for the start and end rank.
