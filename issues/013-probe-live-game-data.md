---
id: 13
title: "Probe live game data sources in a real TFT game"
labels: [wayfinder:task]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

What do the local data sources actually return during a live TFT game on the owner's PC, now that TFT runs on Unreal Engine? This is a HITL task: the owner plays one game while the agent runs read-only probes. Record:

- Whether Riot's Live Client Data API answers, for example `curl -k https://127.0.0.1:2999/liveclientdata/allgamedata`, and which fields it returns.
- Which client is in use (the League client or the dedicated TFT client, if it has shipped).
- Screenshots of the planning phase at the owner's resolution, for judging OCR and vision feasibility. They should show the HUD, shop with a Wisp, board and bench.

The results feed "Game-state capture route".

Run this after 2026-10-06, when Vanguard starts blocking game-memory access for unknown third-party apps (see "Riot third-party app policy for real-time TFT advice"). If an Overwolf developer build is available by then, also record which Overwolf TFT game-event keys still update.

## Comments

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": also screenshot one or two scouted opponent boards (with the bench if it shows), so the probe can judge whether screen capture reads opponents' boards well enough for the contested count.

### 2026-10-04 — claude-code

Input from "Econ, level and roll Line simulation": during the probe game, also record rules facts the simulator currently takes as defaults: whether a PvE round keeps, breaks or ignores a win or loss streak; the gold that PvE orbs drop in each PvE round; and whether the Wisp's 4-champion shop alternates per round or per roll (and what the shop shows after a Wisp is bought). Each confirmed fact replaces a default in the per-patch static file.
