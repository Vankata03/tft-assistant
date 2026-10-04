# Patch-day and new-set workflow

Part of the [MVP spec](../spec.md). Sources: [Patch-day and new-set workflow](../../issues/028-patch-day-and-new-set-workflow.md), [Data source strategy](../../issues/010-data-source-strategy.md), [Evaluation harness](../../issues/027-evaluation-harness.md), [Positioning decisions](../../issues/022-positioning-decisions.md), [Record the pre-coach baseline](../../issues/016-record-pre-coach-baseline.md), [Benchmark open-source board recognition on probe frames](../../issues/024-benchmark-board-recognition.md), [Current TFT set and its mechanics, including wisp](../../issues/005-current-set-mechanics.md), [TFT econ, level and roll math and established theory](../../issues/006-econ-level-roll-theory.md).

TFT patches about every two weeks and ships a new set about every four months. Statistics refresh on their own ([data.md](data.md)); this workflow covers the hand-kept files, overrides and recognition assets. Numbers come only from Riot patch notes and game data, never from third-party guides.

## Static file

- `uv run tft-data new-patch <patch>` copies the previous patch's static and tunables files to `data/<patch>/`, refreshes every field CommunityDragon and Data Dragon carry (Wisp text and values, the augment list, names and costs), adds the patch to `data/patches.toml`, and writes a patch-day diff report: every changed field, every new or removed id, and the threat-tag diff.
- An agent session then fills the fields the patch notes change, citing the patch-note line for each. The owner reviews the diff and commits.
- **Schema check.** Every field holds a value and a `source` tag: `cdragon`, `ddragon`, `patch-notes`, `carried` or `default`. A missing field fails the load, and so does a new id without an entry, such as a new Wisp with no effect kind. A `carried` field on an entity the patch notes name raises a warning. Live mode lowers confidence on `default` and `carried` fields.
- The Baseline-mode Wisp worth table is recomputed from the committed file.
- The threat keyword lists are per-set data in the static file, hand-kept and carried over each patch.

## Tunables file

A new patch's tunables file starts as a whole copy of the previous patch's.

- **Family 1 (fitted)** carries over. Refits stay on the 10-game block boundary and use every game of the current set, with no patch weighting. A patch inside a block does not trigger a refit.
- **Family 2 (margins)** carries over, because Monte Carlo and model noise do not change with a patch.
- **Hand-set** tunables carry over. **Computed** tunables (`opponent_growth_curve`, `default_lines_by_carry_cost`) recompute at each refresh.
- **Family 3 (priors)** is recomputed by `uv run tft-harness fit --priors` at the first refresh in which the new patch's statistics pass about 500 boards; until then the old priors stay. The candidate is accepted by commit.
- The harness first runs on a patch's own games at the next normal 10-game block.

## Owner overrides

- Every entry carries over by default, keyed by a stable unit, augment, item or comp id, and may carry an optional `until_patch`.
- An entry whose id is missing from the current data snapshot is stale: it is ignored and listed in a second-screen warning, and it never fails the load.
- An entry for an entity flagged "changed this patch" stays active and is listed under "review".
- At a new set the whole file is archived as `overrides-set<N>.toml` and a fresh file starts empty.

## Threat tags

There is no gate. New and changed derived tags apply at once. Their diff, with the matched phrases, is a section of the patch-day diff report, and the owner corrects mistakes through the override file's threat-tag section.

## Patch keying

- The coach's own game logs need no calendar: each game records the patch label of the data snapshot it started with.
- The calendar serves only match-API games: the pre-coach baseline and the final boards used for board power fits. It is the hand-kept `data/patches.toml`, one line per patch with its EUNE live date and time, written by `tft-data new-patch` with the date the owner confirms.
- Games within one day of a boundary are marked uncertain and dropped from patch-split statistics.

## Readiness on patch day

- Until the new static file is committed, Live mode runs on the previous patch's static file with a banner naming that patch.
- Sub-engines that read a table the patch may have changed (Wisp, econ augments, Line simulation) lower their confidence.
- A new id with no static entry silences only the advice that needs it; an unknown Wisp, for example, gets no Wisp call.
- These games count toward the 50 Live-mode games, with a game-log flag so the harness can split them out.
- HUD-layout drift after a patch needs no extra mode: fields that fail to read go stale and silence their sub-engine.

## Training-crop pipeline

This is needed within Set 18, not only at a new set, because the board reader misses Lux's Avatar forms and board views of 5-costs.

- After each game, crops are cut from the game log's keyframes by health bar, using the fixed bar window.
- A crop is labelled automatically only when the label is unambiguous: every other crop on the keyframe matches confidently and exactly one unit that purchase tracking says the player owns remains. Star levels come from purchase tracking's copy count. Everything else goes to an unlabelled pile.
- `uv run tft-train` fine-tunes the EfficientNet-B0 classifier on the CPU, offline and by hand.
- A candidate is accepted only if it scores at least as well as the current model on a held-out labelled set, with no class worse beyond noise.
- Model files live outside git under `%LOCALAPPDATA%\tft-assistant\models\`. The accepted model is a version pointer committed in the repository, and each game log records the model version.

## New set

The spec gives a repair checklist and a contract, not a design for the next set's mechanic. Repair order:

1. The static file, from scratch, including the threat keyword lists.
2. Name lists and icon templates, automatic from CommunityDragon and Data Dragon.
3. The Guides and statistics mapping, with each adapter re-checked against its schema.
4. A board-recognition retrain.
5. The set-mechanic plug-in.

The set mechanic's sub-engine (the Wisp sub-engine in Set 18) is a per-set plug-in behind the same `fit(comp, state)` and same-seed Line-simulation-pair interface, rewritten each set. Designing the next one is a new-set effort, out of scope for v1.

At a new set, family 1 tunables carry over as starting values and are refitted after the first 10 games, priors recompute, margins carry over, and set-specific tunables such as `wisp_buy_margin` are dropped.

## Measurement window

The 50 Live-mode games must finish within Set 18. If they cannot, the run restarts in the new set with a fresh pre-coach baseline.
