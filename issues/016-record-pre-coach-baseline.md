---
id: 16
title: "Record the pre-coach baseline"
labels: [wayfinder:task]
status: closed
assignee: Ivan Terziev
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

### 2026-10-04 — claude-code (resolution)

Resolved with the owner. The pre-coach baseline is rolling: a snapshot now from games already played, refreshed just before the first Live-mode game.

- **Which games count**: the last 50 ranked games (queue `1100`) played without the coach, from any patch of the same set as the Live-mode games. Double Up, Hyper Roll and normal games do not count. A baseline from another set does not count, because the set's mechanics and champions change. If the set has fewer than 50 no-coach ranked games when Live mode is ready, the owner plays the missing ones first.
- **Refresh**: just before the first Live-mode game, pull the owner's match history again and take the last 50 no-coach ranked games of the current set. They replace this snapshot as the figure the 50 Live-mode games are compared against.
- **Snapshot (2026-10-04)**: the owner's 50 most recent matches are all Set 18 ranked games, played from 2026-09-12 to 2026-10-03. Average placement 4.62, standard deviation 2.49, standard error of the mean 0.35. Top 4 in 23 games (46%), 8 firsts, 10 eighths. Distribution: 1st ×8, 2nd ×5, 3rd ×5, 4th ×5, 5th ×9, 6th ×3, 7th ×5, 8th ×10. Placements, oldest first: 1 2 2 1 5 8 6 8 2 6 3 7 5 7 5 1 4 7 4 8 6 4 4 5 3 1 1 1 8 7 8 8 8 2 8 1 5 5 5 8 7 1 2 5 8 3 3 5 3 4.
- **Rank**: Platinum III, 59 LP on 2026-10-04 (`tft-league-v1`: 49 wins, 49 losses). Riot keeps no rank history, so the rank at the start of the 50 games cannot be recovered. Rank is context; the comparison uses average placement.
- **Noise**: with a standard deviation of about 2.5, the difference between two 50-game averages has a standard error of about 0.5. Only a large improvement will stand out from noise.
- **Raw data**: match IDs, dates and placements are in `$HOME\.config\tft-assistant\baseline-matches.json`, outside the repository. The repository holds no match IDs and no PUUID.
- **How it was pulled**: `account-v1` by Riot ID (region `europe`) for the PUUID, `tft-league-v1` by PUUID (platform `eun1`) for the rank, `tft-match-v1` match IDs (`count=200`) and match details (region `europe`), filtered on `info.tft_set_number` and `info.queue_id`, at about one request per 1.25 s to stay under the 100 per 2 minutes app limit. The script was a throwaway; a build session rewrites it for the refresh.

Two facts for later tickets:

- `info.game_version` is the literal `TFT Unreal Version ?.?.?.?` for every Set 18 game, so the match API no longer gives the patch. Splitting matches by patch, including any self-aggregation, has to map game dates to the patch calendar.
- Riot's API sits behind Cloudflare, which rejects Python's default `urllib` User-Agent with HTTP 403 `error code: 1010`. Every client sends its own User-Agent.

### 2026-10-04 — claude-code

Input from "Evaluation harness": the coach can run silent games, capturing and logging a game while showing nothing (no advice, no Guides, no highlights). A silent game counts as a no-coach game for the pre-coach baseline as long as the owner opens no review of it before the Live-mode run starts. Playing the baseline's ranked games as silent games gives the evaluation harness game logs to fit and calibrate against before the first Live-mode game.
