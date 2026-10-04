# Data sources and refresh

Part of the [MVP spec](../spec.md). Sources: [TFT stats data sources and their APIs](../../issues/004-stats-data-sources-and-apis.md), [Data source strategy](../../issues/010-data-source-strategy.md), [Augment decisions](../../issues/021-augment-decisions.md), [Register a Riot personal API key](../../issues/017-register-riot-personal-api-key.md), [Record the pre-coach baseline](../../issues/016-record-pre-coach-baseline.md), [Stack and runtime](../../issues/025-stack-and-runtime.md), [Patch-day and new-set workflow](../../issues/028-patch-day-and-new-set-workflow.md), [Data refresh trigger and silent sessions](../../issues/033-data-refresh-trigger-and-silent-sessions.md).

## Sources

Every source sits behind its own adapter, so a source can be swapped by replacing one module.

- **Statistics.** MetaTFT's undocumented JSON is primary; tactics.tools is secondary. There is no Riot API crawler in v1. Statistics default to Diamond and above, all regions; the filter is configurable. Neither site licenses reuse. Self-aggregation from the Riot API is the route for a public release, which is out of scope.
- **Guides.** TFT Academy's embedded comp records are the base: 65 Set 18 comps, each with tier, early and final board, carousel, augments, stage tips and alternative builds. Statistics fill in item and augment rankings. The owner override file wins over both. lolchess is excluded because its terms forbid copying; Blitz is not a source.
- **Positioning.** Final boards use TFT Academy's `finalComp[].boardIndex` (0 to 27). Interim boards, and units TFT Academy does not place, use MetaTFT's per-unit cell histogram (`comp_details` → `positioning`). The owner override wins.
- **Interim boards.** The static interim board per comp is TFT Academy's `earlyComp` (units and items, no positions). No source has early-board statistics.
- **Static game data.** Data Dragon (names, icons, costs) and CommunityDragon (ability and trait numbers and text, Wisp text and values) are fetched automatically and need no key.
- **The per-patch static file** covers what both lack, filled per [patch-workflow.md](patch-workflow.md): the XP, gold, streak, interest and damage tables, shop odds and pool sizes, rules flags, each Wisp's effect kind and values, combat-buff board power bonuses, the per-round Wisp cap, opening encounters' effects, econ augment tags with their effects, and each tier's augment pool.
- **Data no source records**: positioning statistics, econ and HP curves, roll-down timing and augment offers. The Engine uses game maths and Guides for these. The coach logs every captured game, but v1 does not depend on that personal dataset for statistics.

## Augment data for Set 18

No source publishes Set 18 augment statistics. The Riot match record has no `augments` field, MetaTFT's explorer returns null augment ids, and tactics.tools has an empty augment table. What exists is curated tiers:

- MetaTFT `comp_augment_tiers?cluster_id=<id>`: per comp, tiers S, A and B.
- MetaTFT `tft-stat-api/augments_tiers`: a global curated list (S, A, B, C).
- TFT Academy's per-comp `augments` lists, used as a display tag and tie-break.

The statistics path stays in the design and switches on per augment once a source publishes rows past the sample threshold ([sub-engines.md](sub-engines.md#augments)).

## Data snapshots and refresh

- A **data snapshot** is the statistics, Guides and static data fetched in one refresh. It is an immutable directory and never changes once written. A game uses the data snapshot it started with from start to end, and each game log records its patch label.
- **When.** At core start, and whenever the League client API reports the `Lobby` phase or the end of a game; never during a game. Every trigger runs the check below. There is no overall age gate on the data snapshot, because a flat gate would hold statistics back on patch day, when they move fastest. A refresh never blocks queueing; if a game starts first, the refresh finishes after it.
- **What.** Each refresh checks every source's update timestamp and patch label, and pulls only data that has changed and is past its own minimum age: 1 hour for statistics, 6 hours for Guides, and on patch change for static data. The check costs a few small requests. A new data snapshot is written only when something was pulled.
- **Patch day.** Each entity uses new-patch statistics once its sample passes about 500 boards. Below that it uses previous-patch statistics flagged stale. Entities the patch notes changed carry a separate "changed this patch" flag. Live mode lowers confidence on flagged entities.
- **Breakage.** Every response is checked against an expected schema. On failure the coach keeps the last good snapshot, falls back to tactics.tools for unit, item and augment statistics, and shows a visible "data stale since" warning. The coach always runs.

## Riot API

The Riot API serves only the owner's own matches.

- **Key.** A personal key was submitted on 2026-10-04 and is pending review. Until it is approved, a 24-hour development key serves. The key lives in `$HOME\.config\tft-assistant\riot-api-key`, one line, outside the repository. Tools read it from the file and never print it.
- **Limits.** App limit 20 requests per second and 100 per 2 minutes, per routing value; this is the binding limit.
- **Routing.** The owner plays on EUNE. Platform `eun1` serves `tft-summoner-v1` and `tft-league-v1`; region `europe` serves `account-v1` and `tft-match-v1`. Everything is keyed on the PUUID; `tft-summoner-v1` returns no encrypted summoner id.
- **User-Agent.** Riot's API sits behind Cloudflare, which rejects Python's default `urllib` User-Agent with HTTP 403 `error code: 1010`. Every client sends its own User-Agent.
- **No patch in match records.** `info.game_version` is the literal `TFT Unreal Version ?.?.?.?` for every Set 18 game. Match-API games are mapped to patches through `data/patches.toml` ([patch-workflow.md](patch-workflow.md#patch-keying)).
- **Uses.**
  - The owner's final boards (about 800 boards from 100+ matches) for fitting board power's global weights.
  - Refreshing the pre-coach baseline, done once by `uv run tft-harness start-run`, which then freezes it ([review-and-harness.md](review-and-harness.md#silent-games) gives which games count): `account-v1` by Riot ID for the PUUID, `tft-league-v1` for rank, `tft-match-v1` match ids and details filtered on `info.tft_set_number` and `info.queue_id`, paced at about one request per 1.25 s. A build session rewrites the throwaway script used on 2026-10-04. Raw match data stays in `$HOME\.config\tft-assistant\baseline-matches.json`; the repository holds no match ids and no PUUID.
  - Post-game review: final placement, elimination order and all eight final boards (units, stars, items, traits).
