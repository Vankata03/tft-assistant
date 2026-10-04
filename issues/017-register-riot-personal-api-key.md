---
id: 17
title: "Register a Riot personal API key"
labels: [wayfinder:task]
status: closed
assignee: Ivan Terziev
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

## Comments

### 2026-10-04 — claude-code (resolution)

Resolved with the owner. The owner submitted the personal API key application on 2026-10-04 with Game Focus set to Teamfight Tactics. Riot has not reviewed it yet. Until it is approved, the coach uses the 24-hour development key, and the owner regenerates it on the portal (CAPTCHA) on days they play. The decision in "Data source strategy" stands: the personal key replaces the development key once approved.

- **Key location**: `C:\Users\Vankata\.config\tft-assistant\riot-api-key` (`$HOME\.config\tft-assistant\riot-api-key`), one line holding only the key, outside the repository. Regenerating a key means overwriting this file. Tools read the key from the file and never print it.
- **App rate limits** (development key, from `X-App-Rate-Limit`): 20 requests per second and 100 requests per 2 minutes, enforced per routing value. The portal states the same limits.
- **Method rate limits** (from `X-Method-Rate-Limit`): `account-v1` by Riot ID 1,000 per 60 s; `tft-match-v1` match IDs by PUUID 400 per 10 s; `tft-summoner-v1` by PUUID 1,600 per 60 s; `tft-league-v1` by PUUID 20,000 per 10 s and 1,200,000 per 600 s. The app limit is the binding one.
- **Routing**: the owner plays on EUNE. Platform `eun1` serves `tft-summoner-v1` and `tft-league-v1`; region `europe` serves `account-v1` and `tft-match-v1`.
- **tft-summoner-v1**: answers 200 with the development key. The body holds only `puuid`, `profileIconId`, `revisionDate` and `summonerLevel`; there is no encrypted summoner ID, so the coach keys everything on the PUUID. Whether it also answers with the personal key can only be checked once that key is approved, but nothing downstream needs this endpoint.
- **tft-league-v1** by PUUID answers 200 and returns `queueType`, `tier`, `rank`, `leaguePoints`, `wins` and `losses`. This supplies the start and end rank for "Record the pre-coach baseline" with no summoner ID.
- **Match history**: a request for 100 match IDs returned 100, so the owner has at least 100 matches available. The list mixes every TFT queue, so the baseline must filter on queue (ranked) and set from each match's details.

Checked with a throwaway read-only probe script that the owner ran in their own terminal. The current development key appeared in a chat screenshot during this session; it expires on 2026-10-05 at 01:11 PT.
