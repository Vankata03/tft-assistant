---
id: 17
title: "Register a Riot personal API key"
labels: [wayfinder:task]
status: open
assignee:
parent: 1
blocked_by: []
---

## Question

Register a personal API key on the Riot developer portal (https://developer.riotgames.com) for the owner's own match history. This is a HITL task: the owner signs in and submits the registration, because an agent cannot create accounts or enter credentials. The application should describe a personal tool that reads only the owner's own TFT matches.

Record:

- Where the key is stored locally (never in the repository).
- The app and method rate limits the key reports. Read them from the `X-App-Rate-Limit` and `X-Method-Rate-Limit` headers of one `tft-match-v1` call.
- Whether `tft-summoner-v1`, which Riot labels "Teamfight Tactics RSO", works with a personal key.

The key unblocks "Record the pre-coach baseline" and serves "Post-game review scope". The decision is recorded in "Data source strategy".
