---
id: 28
title: "Patch-day and new-set workflow"
labels: [wayfinder:grilling]
status: open
assignee:
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
