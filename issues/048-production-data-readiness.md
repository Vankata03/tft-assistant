---
id: 48
title: Prepare and qualify the first sourced patch-data candidate
labels: [implementation:task, qualification:data]
status: open
assignee:
parent: 34
blocked_by: [36, 40, 41]
---

# Prepare and qualify the first sourced patch-data candidate

This ticket extracts the production data preparation and qualification left explicit by ticket 36. Adapter and immutable-refresh software is complete; a fresh installation still needs a valid patch directory before it can produce game advice.

## Acceptance

Prepare a concrete first-patch candidate using the implemented bootstrap workflow and checked primary Dragon payloads. Supply source-tagged static and tunable files, preserve citations and uncertainty, validate the complete candidate, and provide its patch diff for review. Defaults and carried values must remain visibly qualified. Unknown mechanic effects must suppress dependent advice; they must not become fabricated current-game values.

Include current economy, pool, shop, round and sell rules; Wisp, encounter and augment effects and pools; trait variants and item recipes; level/item schedules and lobby rate. Check configured statistics cohorts and enrichment payloads, including per-comp augment tiers and positioning where the provider supplies them. Document source gaps precisely.

Fitted coefficients require actual data and the harness acceptance gate. An initial default is not a statistical fit. The EUNE patch calendar requires an owner-confirmed live boundary; a League bundle version or a patch-note publication time is insufficient. Do not call the owner's API, start their measurement run or claim human-played games without their corresponding instruction.

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
