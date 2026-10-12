---
id: 48
title: Prepare and qualify the first sourced patch-data candidate
labels: [implementation:task, qualification:data]
status: open
assignee: implement/ticket-48
parent: 34
blocked_by: [36, 40, 41, 51, 54, 56]
---

# Prepare and qualify the first sourced patch-data candidate

This ticket extracts the production data preparation and qualification left explicit by ticket 36. Adapter and immutable-refresh software is complete; a fresh installation still needs a valid patch directory before it can produce game advice.

## Acceptance

Prepare a concrete first-patch candidate using the implemented bootstrap workflow and checked primary Dragon payloads. Supply source-tagged static and tunable files, preserve citations and uncertainty, validate the complete candidate, and provide its patch diff for review. Defaults and carried values must remain visibly qualified. Unknown mechanic effects must suppress dependent advice; they must not become fabricated current-game values.

Include current economy, pool, shop, round and sell rules; Wisp, encounter and augment effects and pools; trait variants and item recipes; level/item schedules and lobby rate. Check configured statistics cohorts and enrichment payloads, including per-comp augment tiers and positioning where the provider supplies them. Document source gaps precisely.

Fitted coefficients require actual data and the harness acceptance gate. An initial default is not a statistical fit. The EUNE patch calendar requires a qualified live boundary from checked primary deployment evidence or the owner; a League bundle version or a patch-note publication time is insufficient. The owner's October 12 instruction explicitly permits researching the dates from the web rather than requiring remembered dates. Do not call the owner's API, start their measurement run or claim human-played games without their corresponding instruction.

Keep software checks separate from owner review, external-service qualification and live-game evidence. If owner information or unavailable observations remain necessary, prepare every independent artifact first and record the exact unresolved fields rather than closing this ticket.

## Context

See ticket 36's first-install bootstrap command and qualification record. Checked source payloads are cached read-only under ignored `worktrees/references/cdragon/`; `data/sources.toml` contains the source manifest. Current source observations are dated in ticket 36. The canonical software specification remains `docs/spec/data.md`, `patch-workflow.md` and `tunables.md`.

## Comments

### 2026-10-07 — codex (bounded source checks)

Riot's [18.2 patch notes](https://teamfighttactics.leagueoflegends.com/en-us/news/game-updates/teamfight-tactics-patch-18-2/) confirm level 7→8 requires 56 XP; the September 14 update restores 8→9 and 9→10 to 68 XP. These observations support those entries only, not an otherwise unchecked complete table.

Current CommunityDragon set-18 trait `DA_18_LuxUniqueTrait` explicitly says an Avatar's chosen trait counts twice. Each sourced Lux form therefore needs its Origin grant of two and Avatar grant of one in the explicit trait rules. Form aliases share `DA_Lux18_Base` pool identity; they are not independent pool types. The source payload is `latest-en_us.json` in the cache named above.

### 2026-10-10 — codex (mid-patch source refresh)

The checked [Riot 18.4 notes](https://teamfighttactics.leagueoflegends.com/en-gb/news/game-updates/teamfight-tactics-patch-18-4/) now include an October 7 B-patch. Search Party costs 1/0 gold instead of 3/1, and Three Me costs 10 instead of 9. Future Focused grants 5 instead of 8 gold; Heroic Grab Bag starts with 6 instead of 4 gold. Heart of Steel is temporarily disabled. The candidate must account for these updates and the affected availability rules, rather than assuming the October 6 payloads already reflect them. This source check does not establish the EUNE live boundary or qualify the complete static tables.

Current public provider payloads and hash manifests are cached under ignored `worktrees/references/data-refresh-2026-10-10/`. The implemented adapters parsed 209 MetaTFT statistics and 364 Tactics statistics against the checked Dragon catalog. MetaTFT reports patch `18.4` but supplies no confirming cohort metadata. Tactics reports `18.4b`, queue 1100 and rank group 1. The global augment enrichment parsed 259 tiers and supplied no per-comp tier or positioning tables. These observations qualify the inspected shapes only, not statistical fits or every configured cohort.

Academy reports `18.4b` and contains 67 Guides, but the current adapter rejects the source at an unresolved entity. The six unresolved stable IDs across those Guides are `DA_18_RiftbeastTraitAugmentStampede`, `DA_CursedCrown`, `DA_Elderwood18_Lifeblossom`, `DA_Elderwood18_Protector`, `DA_Elderwood18_StonebarkTree` and `DA_NestingDolls`. Exact affected Guide IDs are in `academy-unresolved-ids.json` beside the cache. Resolve these through checked source data or preserve explicit unavailable status; do not fabricate aliases or silently drop units from the layouts.

The October 10 CommunityDragon refresh succeeded after retrying the initial HTTP 403 with a browser User-Agent. Its bytes are identical to the October 7 cache. A complete Data Dragon 16.20.1 champion/item/trait response bundle is prepared at `worktrees/references/cdragon/ddragon-bundle-16.20.1.json`; its League version is not a TFT patch or EUNE boundary.

`worktrees/references/cdragon/named-effect-preflight.json` resolves 1,696 description-variable occurrences against the payload's effect keys using the lowercased FNV-1a BIN hash defined by [CommunityDragon's extractor](https://raw.githubusercontent.com/CommunityDragon/CDTB/master/cdtb/binfile.py). The report retains 136 unresolved occurrences. For example, Pocket Change's `GoldOnDeath` and `UpgradeGoldGranted` each map to an explicit value of 1. This resolves variable identity only; effect conditions, prices, offer stages and model support still require review.

The refreshed CommunityDragon payload is not sufficient evidence that all its numbers are current. Its Varus record still has approximately 0.70 attack speed and 30/120 mana, while the checked 18.4 notes set attack speed to 0.75 and the October 7 update sets mana to 20/110. Champion ability-variable arrays inspected for Varus, Ashe, Alistar and Camille are empty. Preserve this source conflict, use checked patch-note corrections where representable, and do not label absent or conflicting ability values as qualified current data.

### 2026-10-10 — codex (enrichment metadata provenance)

The checked global augment response carries its own `updated` value, `1791641438134` (`2026-10-10T14:10:38.134Z`), and `content.updated_at=2026-10-10T05:21:29.598Z`. It identifies `TFTSet18` and queue 1100 but supplies no confirming patch, rank or region. `data/sources.toml` currently points this enrichment's `metadata_url` at the different `unit_items_processed` payload. Candidate qualification must preserve the tier response's own publication timestamps and explicit unknown patch/cohort rather than present the unit response's patch or freshness as established tier metadata. The bounded preflight notes remain outside tracked production data until this ticket is unblocked and the provenance handling is implemented and verified.

### 2026-10-11 — codex (post-Engine contract inventory)

After the ticket 40 merge, runtime inspection of `tft_data.config` confirms 24 required static fields and 58 required Set-18 tunables: family 1 has 14, family 2 has 10, family 3 has 7, hand-set has 25, and computed has 2. The October 10 preflight's count of 56 predates `terminal_gold_weight` (family 1) and `opponent_inference_state_cap` (hand-set). Recheck final consumer shapes after ticket 41; these counts and the preflight are not a qualified production candidate or fitted parameters.

### 2026-10-12 — codex (isolated review artifacts)

Prepared local review inputs under ignored `worktrees/candidate-prep-18.4b-2026-10-12/` using the actual integrated Dragon adapters and checked October 10 cached bytes. `prepare.py` writes `catalog-review.json`, `recipe-review.json`, `item-grant-coverage.json`, `wisp-support-coverage.json`, `source-gap-diff.json`, `consumer-input-ledger.json` and a hashed `manifest.json`. The catalog has 65 units, 9 unit forms, 17 NPCs, 36 traits, 423 items, 592 augments and 349 Wisps. Its 94 recipes reference existing canonical IDs. Data Dragon merges are restricted to the scoped CommunityDragon identities.

The coverage ledgers preserve all 423 unknown item-grant certificates and 349 unknown Wisp price/stage/refill contracts. Named effect evidence, dated patch-note corrections, unresolved Guide IDs and provider observations remain review evidence. The provider observations predate ticket 51 and do not certify opaque enums as configured cohorts. All 24 static fields and 58 tunables remain unresolved template entries; no defaults, carried values or fits were installed. The consumer ledger cites the unfinished ticket 41 contract by its inspected hash, so it must be reconciled with the exact merged commit.

The first immediate-repeat check detected changed output and exited 1; its initial output hashes were not retained, so the changing field is unknown. A bounded follow-up produced no byte diff. The final repeat check passed: all seven JSON files were byte-identical, all six output hashes and input hashes matched, 1,491 entities round-tripped through the public immutable constructors, all 94 recipe references resolved, and unresolved-value/publication boundaries held. The final manifest SHA-256 is `1627db366f7296ac61df02435cf7dbc7a5b316e733debb4596ca737e8deeb700`. Draft inputs can change during implementation; these hashes identify the inspected bytes, not a promise that later worktree contents match them.

No patch bootstrap, production snapshot validation, source fetch, owner API, calendar mutation, fit or production publication ran. These artifacts complete independent preparation work only; this ticket stays open for the missing source, representation, owner-boundary and qualification requirements.

### 2026-10-12 — Official calendar research

At the owner's instruction, checked Riot's [TFT schedule](https://support.riotgames.com/en-us/tft/events/patch-schedule-teamfight-tactics) and [18.4 notes](https://teamfighttactics.leagueoflegends.com/en-gb/news/game-updates/teamfight-tactics-patch-18-4/). The schedule lists October 7, 2026 in Pacific Time. The notes' publication timestamp is `2026-10-06T18:00:00.000Z`; the B-patch section is headed October 7 and describes PC rollout before mobile. These are different evidence fields, not an exact regional deployment instant.

Inspected Riot's public status bundle to resolve the Teamfight Tactics/League URLs and `EUN1` deployment. All four current/archived public EUNE feeds returned HTTP 200 with no incidents or maintenances. This does not establish a complete deployment history or an exact live boundary. HTTP bytes, hashes and the typed review artifact are under ignored `worktrees/references/riot-calendar-2026-10-12/`; `calendar-review.json` SHA-256 is `76bb16158001b0b920749c99a8ef4c2ddfb6ef53dcf7942e2a793ff90ec73568`. Schedule/publication/section dates are retained; exact `18.4` and `18.4b` EUNE timestamps remain unavailable. No production calendar or owner API was changed.
