---
id: 28
title: "Patch-day and new-set workflow"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: []
---

## Question

What happens to the coach's hand-kept data, tunables, overrides and recognition assets when TFT patches (about every two weeks) and when a new set ships (about every four months)? Data refresh from the statistics sources is settled in "Data source strategy": refreshed between games, never during one, with each game keeping the data snapshot it started with.

Decide:

- **Static file.** Who fills the per-patch static file and how: the XP, gold, streak, interest and damage tables, the rules flags, the econ augment tags with their effects and each tier's augment pool ("Augment decisions"), and each Wisp's effect kind and values, the per-round Wisp cap and the opening encounters' effects ("Shop, Wisp and carousel decisions"). How much comes from CommunityDragon and Data Dragon, how much is typed from patch notes, and how the schema check catches what is missing. The Baseline-mode Wisp worth table is recomputed from this file each patch.
- **Tunables file.** How a new patch's tunables file starts. "Evaluation harness" split the tunables into three families: fitted on game logs, margins set from noise, and priors from public statistics. Decide whether fitted values and margins carry over from the previous patch, whether priors recompute at the first refresh, and when the harness first runs on a patch's own games.
- **Owner overrides.** How the override file (TOML in `$HOME\.config\tft-assistant\`) survives a patch: which entries expire, which carry over, and how stale entries, such as a unit or augment that was removed, are flagged.
- **Threat tags.** The patch-day review of threat tags derived from CommunityDragon text: their diff and their logged matches ("Positioning decisions").
- **Patch keying.** The match API's `game_version` no longer names the patch ("Record the pre-coach baseline"), so anything keyed on patch maps game dates to a patch calendar. Decide where that calendar comes from.
- **New set.** What a new set breaks and the order of repair: the static file from scratch, a retrained board-recognition model, refreshed screen regions and icon templates ("Game-state capture route"), the Guides and statistics mapping, and whether any fitted tunables survive. Also the training-crop pipeline from game-log keyframes labelled by purchase tracking, which the board reader already needs within Set 18 for 5-costs and Lux's Avatar forms ("Benchmark open-source board recognition on probe frames"), so it is shared work, not only a new-set task.
- **Readiness.** What the coach does on a patch day before the files are updated: run on the previous patch's files at lowered confidence, fall back to Baseline mode, or stay off.

## Comments

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: "Data source strategy", "Evaluation harness", "Positioning decisions", "Shop, Wisp and carousel decisions", "Augment decisions", "Econ, level and roll Line simulation", "Record the pre-coach baseline", "Benchmark open-source board recognition on probe frames", "Game-state capture route" and "Stack and runtime".

- **Static file.** A script plus an agent session fills it. `uv run tft-data new-patch <patch>` copies the previous patch's file to `data/<patch>/`, refreshes every field CommunityDragon and Data Dragon carry (Wisp text and values, the augment list, names and costs), and writes a patch-day diff report listing every changed field and every new or removed id. An agent session then fills the fields the patch notes change, citing the patch-note line for each. The owner reviews the diff and commits. Scraping patch notes is rejected because their format breaks scrapers; typing everything by hand is rejected as an unsustainable fortnightly chore.
- **Schema check.** Every field holds a value and a `source` tag: `cdragon`, `ddragon`, `patch-notes`, `carried` or `default`. A missing field fails the load, and so does a new id without an entry, such as a new Wisp with no effect kind. A `carried` field on an entity the patch notes name raises a warning. Live mode lowers confidence on `default` and `carried` fields. The Baseline-mode Wisp worth table is recomputed from the committed file.
- **Tunables file.** A new patch's tunables file starts as a whole copy of the previous patch's.
  - Family 1 (fitted) carries over. Refits stay on the 10-game block boundary and use every game of the current set, with no patch weighting in v1. A patch inside a block does not trigger a refit.
  - Family 2 (margins) carries over, because Monte Carlo and model noise do not change with a patch.
  - Family 3 (priors) is recomputed by `uv run tft-harness fit --priors` at the first refresh in which the new patch's statistics pass the sample threshold of about 500 boards; until then the old priors stay. The candidate is accepted by commit like any other.
  - The harness first runs on a patch's own games at the next normal 10-game block. Nothing about it is patch-specific.
- **Owner overrides.** Every entry carries over by default, keyed by a stable unit, augment, item or comp id, and may carry an optional `until_patch`. An entry whose id is missing from the current data snapshot is stale: it is ignored and listed in a second-screen warning, and it never fails the load. An entry for an entity flagged "changed this patch" stays active and is listed under "review". At a new set the whole file is archived as `overrides-set<N>.toml` and a fresh file starts empty.
- **Threat tags.** No gate. New and changed derived tags apply at once. Their diff, with the matched phrases, is a section of the patch-day diff report, and the owner corrects mistakes through the override file's threat-tag section. A wrong tag for a few games costs little, because positioning is rule-based and report-only.
- **Patch keying.** The coach's own game logs need no calendar: each game records the patch label of the data snapshot it started with. The calendar serves only match-API games: the pre-coach baseline and the owner's final boards used for board power fits. It is a hand-kept `data/patches.toml`, one line per patch with its EUNE live date and time, written by `tft-data new-patch` with the date the owner confirms. Games within one day of a boundary are marked uncertain and dropped from patch-split statistics. CommunityDragon directory dates (publication, not go-live) and scraping Riot's patch-notes page were rejected.
- **New set.** The spec gives a repair checklist and a contract, not a design for the next mechanic. Repair order:
  1. The static file from scratch.
  2. Name lists and icon templates, automatic from CommunityDragon and Data Dragon.
  3. The Guides and statistics mapping, with each adapter re-checked against its schema.
  4. A board-recognition retrain.
  5. The set-mechanic plug-in.

  The set mechanic's sub-engine (the Wisp sub-engine in Set 18) is a per-set plug-in behind the same `fit(comp, state)` and same-seed Line-simulation-pair interface, rewritten each set; designing the next one is a new-set effort. Family 1 tunables carry over as starting values and are refitted after the first 10 games, priors recompute, margins carry over, and set-specific tunables such as `wisp_buy_margin` are dropped.
- **Measurement window.** The 50 Live-mode games must finish within Set 18. If they cannot, the run restarts in the new set with a fresh pre-coach baseline.
- **Training-crop pipeline** (shared work, needed within Set 18). After each game, crops are cut from the game log's keyframes by health bar, using the fixed bar window. A crop is labelled automatically only when the label is unambiguous: every other crop on the keyframe matches confidently and exactly one unit that purchase tracking says the player owns remains. Star levels come from purchase tracking's copy count. Everything else goes to an unlabelled pile. `uv run tft-train` fine-tunes the EfficientNet-B0 classifier on the CPU, offline and by hand. A candidate is accepted only if it scores at least as well as the current model on a held-out labelled set, with no class worse beyond noise. Model files live outside git under `%LOCALAPPDATA%\tft-assistant\models\`; the accepted model is a version pointer committed in the repo, and each game log records the model version.
- **Readiness.** Until the new static file is committed, Live mode runs on the previous patch's static file with a banner naming that patch. Sub-engines that read a table the patch may have changed (Wisp, econ augments, Line simulation) lower their confidence. A new id with no static entry silences only the advice that needs it; an unknown Wisp, for example, gets no Wisp call. These games count toward the 50 Live-mode games, with a game-log flag so the harness can split them out. HUD-layout drift after a patch needs no extra mode: fields that fail to read go stale and silence their sub-engine.

Glossary term Set mechanic added to `CONTEXT.md`.

Input posted to "Stack and runtime" (new commands, the patch calendar file and model storage) and "Record the pre-coach baseline" (patch calendar and the Set 18 measurement window).
