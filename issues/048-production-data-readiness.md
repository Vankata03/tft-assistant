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


Ticket 54 retains an active-form producer condition: own variable base identities require a resolved typed active form for rollout valuation. Capture currently preserves its base classifier identity and separate positive traits/origin observations. It does not fabricate a chosen form. Reconcile that producer contract against pinned form metadata before declaring full production/gameplay coverage. Remote slot-budget observations are also not produced; modifier-aware opponent inference returns an explicit qualified par fallback when such evidence is unavailable.

### 2026-10-13 — Final-consumer preparation software and source review

- Resumed `implement/ticket-48` on integration `456646ddee30444107e6cfc62d5a11b6604d327d`, including independently accepted 41/51/54/56 consumers. Safety stash `b959e61add6eb2f090c9e08cc4783b6d2bb8fc5a` preserves the pre-capacity edits; earlier artifacts and other stashes remain untouched. The two merge conflicts were resolved by reusing ticket 54's shared entity overlay and retaining its new-set support.
- Added the public offline `tft-data prepare-review` command and [candidate review workflow](../docs/agents/candidate-review.md). Its required explicit destinations prevent accidental owner-store use. It prepares deterministic identity/recipe/coverage/dependency JSON and a patch diff, hashes inputs and final consumer contracts, and refuses existing destinations. Unknown requirements remain null; it emits no static/tunable TOML. Bootstrap uses the same canonical tagged serializer and shared overlay. Explicit malformed slot certificates fail before review publication; missing ones remain visibly unavailable.
- Public candidate tests: **14 passed, exit 0**. Their positive bootstrap fixture initially failed on missing slot certificates after the 54 merge; it now supplies explicitly cited synthetic ordinary-unit rules. The new required-consumer artifact test failed before implementation. A boolean slot declaration initially published review files incorrectly, then passed the rejection regression after shared validation was added. Data package suite: **58 passed, exit 0**. Final complete train: **478 passed, no skips, 33.36 seconds, exit 0**; the preceding 477-case train passed in 64.90 seconds before the final boolean declaration case. Two existing Torch ONNX export deprecation warnings remain. Import contracts (two kept), schema, lock, scoped Data F821 and diff checks exited 0. No message/UI contract changed. The bounded workflow prose check found zero banned phrases and preserved all 12 extracted constraints.
- Regenerated isolated review artifacts at ignored `worktrees/candidate-prep-18.4b-2026-10-13/final-base/` and `final-repeat/`. All **10 files are byte-identical** and every manifest output hash matches. Final manifest SHA-256: `50c32820e4cf83cac448dd25c78f9cb1bc2a197c0233a64b234f1c7b39355e08`. The catalog's 1,491 identities round-trip through public immutable constructors; all 94 recipe references resolve. Counts remain 65 units, nine forms, 17 NPCs, 36 traits, 423 items, 592 augments and 349 Wisps. Templates now name **25 required static fields and 59 Set-18 tunables**. The ledger distinguishes source rules, policy, fit requirements and captured completeness. Final 41/54/56 contract hashes replace the earlier unfinished-41 reference.
- Partial primary-rule inputs are beside those directories: `entity-review-overlay.json` records only Elder Dragon's checked two-slot declaration; `primary-rule-review.json` preserves Lux's double Origin/single Avatar and Elder's two-total Riftbeast grants, partial XP entries 7→8=56, 8→9=68 and 9→10=68, and the dated B-patch corrections. These are checked source facts and review declarations, not a complete qualified patch. The Riftbeast-10 conflict remains explicit: prelaunch overview +1 versus checked `TeamSize=2`; neither becomes a current capacity rule. The overlay leaves **73 playable slot certificates unknown**. It invents no ordinary-unit fallback, equipment class/reference, item no-grant certificate or Wisp outcome distribution.
- Fresh HTTP bodies, dates and hashes are retained under ignored `worktrees/references/source-refresh-2026-10-13/`. CommunityDragon's bytes are still SHA-256 `17d19792f662cec404aa071492ae9144a2d2677d2eeb1e0d7d8db9b52a47a9c7`. Checked [18.4 notes](https://teamfighttactics.leagueoflegends.com/en-gb/news/game-updates/teamfight-tactics-patch-18-4/) retain the B-section and corrections; the [prelaunch overview](https://teamfighttactics.leagueoflegends.com/en-sg/news/game-updates/enchanted-wilds-overview/) retains its dated capacity statement. Provider metadata was checked through the configured public source boundary: MetaTFT parses 211 statistics and Tactics 364, but neither confirms the requested Diamond/all-regions cohort. Tactics' raw rank-group enum remains separate from canonical cohort evidence. The 259 global augment tiers have their own publication timestamps but no confirmed patch; the donor's `18.4`/B hint remains nonauthoritative. Per-comp tiers and positioning remain absent. Academy confirms `18.4b` metadata but still rejects at `DA_Elderwood18_Lifeblossom`; no alias or dropped Guide hides the failure. The first provider-ledger write failed on datetime serialization; explicit ISO encoding fixed it before ledger publication.
- Rechecked the [official schedule](https://support.riotgames.com/en-us/tft/events/patch-schedule-teamfight-tactics) and four public current/archived EUN1 status feeds. The schedule date, note publication and B-section date remain distinct; all feeds returned HTTP 200 with empty incidents/maintenances. Their hashes match the earlier bodies. Empty feeds do not certify complete deployment history or an exact EUNE live instant. No calendar was written.
- **Production acceptance remains open.** A complete sourced economy/pool/shop/round/sell/capacity file, supported activation policies, all equipped-item grant/class/reference certificates, complete Wisp effects/prices/availability/refill and encounter/augment pools, qualified statistics/enrichment, defaults/priors/fitted coefficients and standard states are still unqualified. All 423 item-grant and 349 complete Wisp contracts remain unavailable in coverage. Round/gold-conditional free Wisp prices cannot become a universally valid stage-only label. Active-form resolution, reviewed own counter semantics/regions and scoped remote budgets still need producer/HUD evidence. No owner API, matches, measurement run, fit, production snapshot, production patch or calendar publication occurred. Fixture and artifact checks do not close this ticket or qualify Windows/game-running behavior.

### 2026-10-13 — Preparation boundary corrections after independent review

Corrected the independently reproduced input-fingerprint race: `prepare-review` reads each Dragon and optional entity-overlay input once, then parses and hashes those exact bytes. Overlay review evidence also hashes the consumed bytes. Output JSON and Markdown are encoded once as UTF-8 and written as bytes, so Windows newline translation cannot invalidate manifest hashes. Malformed Data Dragon bundles now fail through the declared CLI error boundary before publication, including bootstrap. The consumer ledger locates the augment minimum-sample certificate at `Entity.values.statistics_min_samples`, matching the Engine; it remains an unresolved review field rather than an installed value.

The public CLI regressions reproduced wrong fingerprints using actual external FIFO inputs replaced before EOF for CommunityDragon, Data Dragon and entity overlay. All three cases failed before the correction and passed afterward. Malformed review bundle cases reproduced `AttributeError` before the schema correction and now return error 2 without output. The ledger assertion also failed before correction. The repeat-output check includes non-ASCII UTF-8 and CRLF input bytes, verifies LF output bytes and every output manifest hash. Data package checks passed: 65 tests, no skips, exit 0 on macOS. Windows execution remains unperformed; the output-byte correction removes text newline translation by construction.

Merged the latest integration branch before handoff. Safety stash `b959e61add6eb2f090c9e08cc4783b6d2bb8fc5a` remains untouched. This ticket stays open: no production values, assets, source fetch, owner API, matches, measurement run, fitted model, regional calendar or production publication was added.

### 2026-10-14 — Independently integrated preparation software

Corrected exact `6ab4544153b530cbdaed5a99ee0ffcf20c86097e` was independently reviewed and merged as `d6d9e6e07496242664aca72272a713ae985e20f7`. Public preparation now freezes each consumed input once, fingerprints those exact bytes, writes exactly the hashed UTF-8 output bytes, rejects malformed Dragon bundles through CLI error 2 without publication, and identifies the Engine's entity-level minimum-sample policy. Three external FIFO replacements reproduce and verify the input race correction.

Independent Data verification passed 65 tests in 0.35 seconds. Combined root verification passed 491 Python tests without skips in 39.18 seconds, process exit 0; two existing Torch ONNX-export warnings remain. UI passed 35 tests and type/generated-type/build checks. Both import contracts, schema, frozen lock, scoped F821 and whitespace gates passed. With Live physically absent, 210 public capacity/lobby/Baseline/capture/replay/Data cases passed in 8.33 seconds, process exit 0; Live and the training group were restored.

Ticket 48 remains open. This verifies preparation software and byte provenance, not current production rules, source/cohort eligibility, mechanics, fitted parameters, recognition accuracy, exact EUNE calendar boundaries or Windows/device behavior. No production candidate or owner measurement run was published.

### 2026-10-20 — Claude (Windows source refresh and review preparation)

The earlier caches lived on the macOS machine, so the sources were fetched again on Windows into ignored `worktrees/references/source-refresh-2026-10-20/`. CommunityDragon `latest/cdragon/tft/en_us.json` (Last-Modified 2026-10-19, content metadata `16.20.8248524`) is byte-identical to the October 7–13 cache, SHA-256 `17d19792f662cec404aa071492ae9144a2d2677d2eeb1e0d7d8db9b52a47a9c7`. The Data Dragon bundle (champion, item and trait at 16.20.1) has SHA-256 `b20d1fafe075fc3d5071ad111ad1ace68b8472602615f3c489f67960d89724b5`. Because the CommunityDragon bytes have not changed, the October 10 conflicts with the 18.4 notes (for example Varus attack speed and mana) still apply.

`tft-data prepare-review 18.4b --set 18` ran on Windows into ignored `worktrees/candidate-prep-2026-10-20/base/` and exited 0. The catalog counts are unchanged: 65 units, 9 unit forms, 17 NPCs, 36 traits, 423 items, 592 augments and 349 Wisps. The requirements now list 25 static fields and 60 Set-18 tunables, one more than `candidate-review.md` states; all are uninstalled. `eune_live_at` is null.

The 2026-10-20 probe game confirms `TFTSet18` and queue 1100 from LCU, but its session bodies carry no game version, so they cannot establish which patch was live.

Unresolved owner decisions remain: the patch label and EUNE live boundary, whether visibly qualified hand defaults may stand in for family 1–3 tunables until fits exist, and acceptance of each static table's sources.

### 2026-10-20 — Claude (18.5 EUNE boundary evidence, for owner confirmation)

Checked at 2026-10-20 20:51 UTC:

- Riot's [TFT patch schedule](https://support.riotgames.com/en-us/tft/events/patch-schedule-teamfight-tactics) lists 18.4 on October 7 and 18.5 on October 21, 2026, in Pacific Time, with no time of day.
- The [18.5 notes](https://teamfighttactics.leagueoflegends.com/en-gb/news/game-updates/teamfight-tactics-patch-18-5/) were published at 2026-10-20T18:00:00Z. The [18.4 notes](https://teamfighttactics.leagueoflegends.com/en-gb/news/game-updates/teamfight-tactics-patch-18-4/) still have one mid-patch section, dated October 7, so 18.4b is the live patch until the 18.5 deployment.
- The public EUN1 status feed (`lol.secure.dyn.riotcdn.net/channels/public/x/status/eun1.json`, saved as `worktrees/references/source-refresh-2026-10-20/status-lol.json`, SHA-256 `af9f56bbc209868fc54e441cf494516c14ebf2d8fa35823c241f009fd9cb8baa`) has scheduled maintenance 13736, created 2026-10-19T23:35:13Z. It disables ranked queues from 2026-10-20 16:30 PDT in preparation for patch 16.21, shuts the servers down at 18:00 PDT (2026-10-21T01:00:00Z), and estimates 4 hours of downtime. The notice's `archive_at` is 2026-10-21T05:00:00Z.
- League 16.21 corresponds to TFT 18.5 by the same one-step progression as the current 16.20 content and Data Dragon bundle for 18.4. That mapping is inference, not a Riot statement, and agrees with the schedule date.

No game can be played while the servers are down, so the shutdown instant separates 18.4b games from 18.5 games regardless of when service returns. The proposed boundary is therefore `18.5 = 2026-10-21T04:00:00+03:00` (2026-10-21T01:00:00Z), pending owner confirmation and a recheck of the feed after the maintenance for a delay or cancellation. The exact 18.4b boundary remains unavailable. Because 18.5 replaces it within hours, the first candidate should target 18.5 once CommunityDragon publishes 16.21 data, not 18.4b.

### 2026-10-20 — Claude (18.5 candidate attempt stopped: sources still 16.20)

Checked at 2026-10-20 21:03 UTC, saved in ignored `worktrees/references/source-refresh-2026-10-21/`:

- CommunityDragon `latest/content-metadata.json` still reports `16.20.8248524+branch.releases-16-20.content.release` (Last-Modified 2026-10-19 20:31:26 GMT). Building 18.5 on these entities would carry 18.4 values into the 18.5 candidate, so `prepare-review 18.5` was not run and no static table, tunable table, snapshot or names JSON was produced.
- The EUN1 status feed is byte-identical to the 20:51 UTC copy (SHA-256 `af9f56bbc209868fc54e441cf494516c14ebf2d8fa35823c241f009fd9cb8baa`). Maintenance 13736 is still `scheduled` with no updates since its creation, and the server shutdown (2026-10-21T01:00:00Z) has not happened yet, so completion without delay cannot be confirmed. The committed boundary `18.5 = 2026-10-21T04:00:00+03:00` still needs that post-maintenance recheck.

Still open before the candidate can start: CommunityDragon 16.21 data, the post-maintenance feed recheck, and the owner's choice on family 1–3 tunables (approved hand defaults tagged `default`, or no defaults and a stop after the 25 hand-set and 2 computed tunables).

### 2026-10-21 — Claude (18.4b candidate on 16.20 sources, awaiting owner review)

At the owner's instruction the first candidate targets 18.4b on the unchanged 16.20 sources; 18.5 follows once CommunityDragon publishes 16.21. The owner approved web sources for values no primary source carries and hand defaults for the family 1–3 tunables. Web values are tagged `default`, never `fitted`, so Live mode keeps their confidence lowered.

**Preparation.** `tft-data prepare-review 18.4b --set 18` ran into ignored `worktrees/candidate-18.4b-2026-10-21/review/` and exited 0, with the same catalog counts as before. The reviewed inputs are in `inputs/` beside it (`static.toml`, `tunables.toml`, `entity-overlay.json`, `wisp-evidence.json`), and `REVIEW.md` renders every static field, all 60 tunables and the per-Wisp evidence for owner review.

**New primary source.** CommunityDragon's raw `map22.bin.json` (16.20, Last-Modified 2026-10-19, SHA-256 `6c4819cda6ac8211d0c154df9e7011746deeca812a46b2c9b66e1a5b957590ca`, saved under `worktrees/references/source-refresh-2026-10-21/raw/`) carries the Set 18 shop odds, pool sizes, stage and round structure, streak gold and Wisp `BaseCost`. The shop odds, pool sizes, round order and types, streak gold, augment tier pools, item recipes and trait rules come from CommunityDragon. The augment tiers use tier tags whose meaning is inferred: every augment has exactly one, and 578 of 592 agree with their icon suffix.

**Web and probe sources.** XP, income, interest, player damage, sell values and the level calendar come from the 18.2 and 18.4 notes, tftips.app, LittleBuddyBot, Noxu, TFT Lab, the League wiki and a Set 17 leveling guide, and each citation is in the TOML. Probe frames `192143_762.png` and `194426_421.png` confirm Buy XP 4, Reroll 2, five shop slots, the level 3 and level 6 odds, the 3→4 and 6→7 XP steps, and team slots equal to level. Wisp prices and offer windows for 344 of 349 catalog Wisps come from tftips.app (18.4b). Those prices agree with the 18.4 notes, while the bin's `BaseCost` is stale for Search Party, Three Me, Forest Guide and Improved Reach. Blossom and Prismatic variant prices use the bin with the 18.4 note corrections. Every Wisp is `unmodelled`, so no Wisp outcome is declared.

**Source conflicts kept visible.** The bin gives level 7 shop odds of 19/30/40/10/1, while tftips and LittleBuddyBot give 16/30/43/10/1; no probe frame reached level 7, so the candidate uses the bin. For player damage at stages 3 and 4, two sources give 6/7 and tft.ninja gives 5/8. Riftbeast (10) adds 2 team slots in CommunityDragon and 1 in the prelaunch overview; the candidate uses CommunityDragon.

**Declared or derived values for owner review.** Ordinary units take one team slot and Elder Dragon takes two. Tactician items use the `equipped_anywhere` scope, which no source confirms. Other declared values are the bench size of 9, `pve_preserves_streak`, `item_slots_max` 3, the threat keyword lists and a `lobby_top4_rate` of 0.5. `stage_items`, `pve_orb_gold` and `component_income_by_stage` are expectations derived from LittleBuddyBot's loot tables; stages 5 and later have no PvE loot table. The 33 family 1–3 tunables are hand defaults with spec rationale. The rollout and state-cap budgets wait on ticket 49 timing.

**Software fix.** 157 CommunityDragon items have a null description, and threat derivation crashed on them, which blocked every real refresh. Commit `cb7f056` treats missing text as matching no phrase and adds a regression test. Data tests: 72 passed, 3 POSIX-only skips.

**Validation.** Bootstrap fails closed: `New Wisp DA_CloneCompanion18 needs a static effect entry`. Five catalog Wisps have no offer window in any source found: `DA_CloneCompanion18`, `DA_CloneCompanion18_Prismatic` and `DA_CloneCompanionUpgrade18` (bin price 5), and `DA_TrueFriendship18` and `DA_TrueFriendship18_Upgrade` (no shop record). A scratch trial gave those five placeholder entries only to surface other errors. With them, bootstrap, `validate` and offline `refresh --engine-computed` all exited 0 with isolated snapshot and override paths. Nothing from that trial is published. The computed growth curve stays empty until online statistics supply unit play rates.

**Remaining gaps.** The gaps are the five Wisp offer windows above and every Wisp, encounter and econ-augment effect. Item category, grant and class certificates are also missing; emblem trait grants are not in CommunityDragon fields. Kha'Zix evolution subsets, the PvE loot for stages 5 and later, and the exact 18.4b EUNE boundary remain unavailable as well. Bootstrap writes no calendar entry. No patch directory, owner snapshot or names JSON is published yet, and no Riot API call or measurement run was made.

### 2026-10-21 — Claude (owner decision on unlisted Wisps; isolated validation passes)

The owner decided that the five catalog Wisps missing from tftips' 18.4b list are not offered on 18.4b. These are `DA_CloneCompanion18`, `DA_CloneCompanion18_Prismatic`, `DA_CloneCompanionUpgrade18`, `DA_TrueFriendship18` and `DA_TrueFriendship18_Upgrade`. Each is now `unmodelled` with offer stages 1–8, which satisfy the schema only. Each takes its bin price, or 0 where the shop record has no price or there is no shop record. The `wisps` citation and `wisp-evidence.json` mark them "not offered on 18.4b".

With these entries, bootstrap into isolated `worktrees/candidate-18.4b-2026-10-21/data/` exited 0. `tft-data validate --snapshots <isolated>` produced snapshot `b94f2e24eb053de845f9903b8d197ee1b255fa94fb1d8f07739f5bee7c2d11ab`. Offline `refresh --engine-computed` with isolated snapshot and override paths produced `2280f0806d588c99820cf1e0d0292f3f494b22b768af8f206a60be0fc146fc3a`; its computed growth curve is unavailable because there are no unit play rates. Publication to `data/18.4b/` and the owner snapshot store waits for the owner's review of `REVIEW.md`.

### 2026-10-21 — Claude (18.4b published after owner review)

The owner reviewed `REVIEW.md` and accepted the tables as they are. Bootstrap published `data/18.4b/`; its `entities.json`, `static.toml` and `tunables.toml` are byte-identical to the isolated validated candidate, and `data/patches.toml` is unchanged. Offline `tft-data refresh --engine-computed` wrote snapshot `2280f0806d588c99820cf1e0d0292f3f494b22b768af8f206a60be0fc146fc3a` to `%LOCALAPPDATA%\tft-assistant\snapshots` and set it as `current.json`. That ID matches the isolated refresh. The computed growth curve stays empty until an online refresh supplies unit play rates.

The en_US names file `%USERPROFILE%\.config\tft-assistant\names\en_US-18.4b.json` (SHA-256 `4380a1dc7a127c4e15f8d27305b14669f0c112f95b10b6d9fd179ac3bfccca61`) is exported from that snapshot's own entity names. It holds 74 units (all 65 playable units plus 9 forms), 423 items, 592 augments, 349 Wisps and 36 traits.

Ticket 48 stays open. The exact 18.4b EUNE boundary, the source gaps listed in the 2026-10-21 candidate entry, statistics-qualified priors and fits, and the 18.5 candidate on 16.21 data remain. No Riot API call or measurement run was made.
