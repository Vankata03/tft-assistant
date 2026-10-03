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
