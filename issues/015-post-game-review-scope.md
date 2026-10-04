---
id: 15
title: "Post-game review scope"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: [9, 11]
---

## Question

What does the post-game review show after a finished game, and what data does it need? Decide which decisions it replays against the engine (every round, or only key moments such as roll-downs, pivots and augment picks), how it presents the gap between the player's choice and the engine's, and where its data comes from: the coach's own capture log of the game, the Riot match API (personal key), or both. Decide whether the review doubles as the evaluation harness for advice quality, which is still in the map's fog.

## Comments

### 2026-10-04 — claude-code

Input from "Data source strategy": the coach logs every captured game from day one, and the owner will hold a Riot personal API key (see "Register a Riot personal API key"), usable only for the owner's own matches. Both data sources named in the question are therefore available.

### 2026-10-04 — claude-code

Input from "Advice engine architecture": the Engine is a pure function of the game snapshot, the game history and the data snapshot, so post-game review replays the captured game log through it round by round and gets the same advice Live mode would have given. Review prose comes from templates; v1 uses no language model. The Engine core runs post-game in both modes. Board and lobby strength is the Engine's weakest part, so if the review doubles as the evaluation harness it should measure that first (see "Board and lobby strength heuristic").

### 2026-10-04 — claude-code

Input from "Transition and pivot domain model": the Game plan is folded from the game history, so replaying the log reproduces every plan change. The review should show pivot calls the player ignored and pivots the player made without a call.

### 2026-10-04 — claude-code

Input from "Econ, level and roll Line simulation": in Live mode the player can pin a Line, and the Engine then follows the pin and only notes when another Line beats it by the line margin. The review should show pinned against recommended Lines, and each round's Line projection (gold, level, probability of having hit the key units, expected HP and expected placement) is available for replay. Free-form what-if editing of a Line was left for after v1, and the review is the natural place for it, because time is free there.

### 2026-10-04 — claude-code

Input from "Board and lobby strength heuristic": board power is measured three ways — final-board ranking on the owner's matches (Spearman correlation and placement MAE, available now), win-probability calibration from fight logs (Brier score, log-loss, calibration by stage), and damage MAE per lost round. Post-game review can show the per-fight win chance against the actual result, and that data feeds the second and third metrics.

### 2026-10-04 — claude-code

Input from "Item decisions": post-game review replays slams, interim holder choices and remover use through the same rules, so it can show where the player held components the coach would have slammed, or locked an item on a unit that was not its holder.

### 2026-10-04 — claude-code

Input from "Augment decisions": the Riot match record for Set 18 has no `augments` field, so augment review depends entirely on the coach's own capture log of offers, rerolls and picks. A game played without a log gets no augment review. The review replays each offer through the same ranking and reroll rules as Live mode.

### 2026-10-04 — claude-code

Input from "Shop, Wisp and carousel decisions": post-game review replays shop buys and sells, Wisp purchases and carousel picks through the same rules as Live mode. This needs the captured shop contents on every roll, the offered Wisps and the carousel options in the game log.

### 2026-10-04 — claude-code

Input from "Probe live game data sources in a real TFT game": the owner reports that TFT Academy's desktop app records each whole game as video and deletes old recordings after a while, so a recording-based review is feasible here too. Lossless frames at 1.6 s cost about 6 GB per game, so a review that keeps footage needs video encoding or keeps only selected frames. The League client's `lol-end-of-game/v1/tft-eog-stats` endpoint is another end-of-game source to check.

### 2026-10-04 — claude-code

Input from "Game-state capture route": the coach keeps a game log per game, keyed by the League client's game id. Structured snapshots (every offer, roll, pick, sighting and fight result, with each field's timestamp and source) are kept forever. Media is a setting: keyframes at decision points by default (each shop after a roll, each augment, Wisp and carousel offer, each scouted board, the end of each planning phase), or full video, capped at 20 GB with the 50 Live-mode evaluation games pinned. A crash leaves a recorded gap. Augments come only from the game log, since the match API no longer records them for Set 18. Every disagreement between vision and purchase tracking is logged with a keyframe, which the review can show.

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: the inputs above, from "Data source strategy", "Advice engine architecture", "Transition and pivot domain model", "Econ, level and roll Line simulation", "Board and lobby strength heuristic", "Item decisions", "Augment decisions", "Shop, Wisp and carousel decisions", "Probe live game data sources in a real TFT game" and "Game-state capture route".

- **Shared replay core, two consumers.** Replaying a game log through the Engine produces a **replay record** for every decision point: the snapshot, the player's choice, the Engine's choice, every option the Engine scored, the estimated cost and the shown-advice status. Post-game review is the per-game view of the replay records for the player. The **evaluation harness** is a separate consumer that aggregates replay records across game logs, computes the board power metrics and checks tunables against them. The review does not double as the harness; the harness graduates from the fog as its own ticket.
- **Data sources.** The game log is required; a game without one gets no review. Its final board still feeds the board power fit, as settled in "Board and lobby strength heuristic". The Riot match API (personal key) adds the final placement, the elimination order and all eight final boards (units, stars, items, traits). The League client's `lol-end-of-game/v1/tft-eog-stats` endpoint is checked during the build as a faster source that needs no key.
- **Coverage.** Every decision point in the game log is replayed. Offline there is no time pressure: about 300 decision points at the 100 ms Engine budget take about 30 s. The review ranks moments by estimated cost and surfaces the top 5 by default, with the full round-by-round timeline below. Replaying only key moments was rejected because it misses slow leaks, such as interest lost over many rounds or bench mis-sells, that only summing reveals.
- **Cost.** The cost of a decision is the Engine's expected placement for its own choice minus its expected placement for the player's choice. It is judged with only the information available at that moment, never with hindsight. The player's actual Line is inferred from the game log (level-ups and roll-downs) and simulated as an extra candidate Line with the same seed as the others. A pinned Line is judged against the recommended Line. A decision whose sub-engine gives no placement value (shop buys use board power gain, carousel picks use a ranked list) is marked "differed" with no cost and ranks below costed decisions. Outcome facts, such as a fight result or whether the key units were hit, are shown as context and never enter the cost.
- **Noise and grouping.** A gap below the tunable `review_min_cost` is a **close call**: it never enters the top moments but stays on the timeline. The default is the larger of the estimate's standard error and 0.05 placement. The same deviation at consecutive decision points (no level-up for three rounds, the same component held for four rounds) merges into one moment with the summed cost.
- **Moment card.** Each moment shows the round (for example 4-1), the category (econ, level and roll; shop; Wisp; items; augments; carousel; transition; pivot), what the player did, what the Engine chose, the estimated cost in placement, a template reason (the top two fit terms, or the Line projection difference in gold, level, hit probability and expected HP), the shown-advice status and the keyframe.
- **What-if in v1.** At each moment the player can pick any option the Engine already scored and see its estimate, with no new simulation. Free-form editing of a Line or a pick, re-simulated through the rest of the game, stays after v1.
- **Shown advice is logged.** The game log records every piece of advice shown, with its timestamp and surface. Replay is deterministic, but live advice can differ from it: a stale field silenced a sub-engine, a read arrived late, or the player pinned a Line. Each moment therefore carries one status: the coach said X and the player did Y (ignored); the coach was silent but would have said X (capture gap); or the player followed the advice and it still cost (Engine error). In Baseline mode the status is "no advice in Baseline mode". The share of advice the player followed is the game's **follow rate**, which helps explain the Live-mode results.
- **Game summary**, at the top of the review:
  - placement, estimated cost per category and follow rate;
  - Game plan timeline: candidate and target comps by round, the commit point, pivots called and taken, pivots called and ignored, and pivots taken without a call;
  - Line chart: the player's actual Line against the recommended Line (and the pinned Line, if any), as level and gold by round;
  - fight strip: for each combat round, win chance against the result and predicted against actual HP lost, as context for luck;
  - debug tab: capture gaps, stale-field silences, and disagreements between vision and purchase tracking with their keyframes.
- **Summing costs.** Per-decision placement deltas compound and overlap, so they do not add exactly. Per-category sums are shown labelled "estimated", and the review never claims a counterfactual placement such as "you would have placed 2nd".
- **Surface and timing.** The review is computed when the League client reports the end of the game, a "review ready" notification appears, and the player opens the review in the second-screen window on demand. There is no voice summary. The layout belongs to "Advice surface UX".
- **Versioning.** Each review is stored with the engine version and the data snapshot id. It is regenerated on demand with the current engine and that game's own data snapshot, so engine fixes show on old games while the patch data stays correct. The evaluation harness re-runs every game log when the engine or the tunables change.
- **Cross-game view.** A game list (date, mode, placement, total estimated cost, worst category) and the average cost per category over the last 10 games and over the 50-game Live-mode run. Pre-coach baseline games have no game log, so they appear with their placement only.
- **Defaults.** Decisions inside a crash gap are not reviewed; the timeline shows the gap. Positioning review follows whatever "Positioning decisions" settles. Baseline-mode games get the same full review, as settled in "Policy stance and feature modes".

**Map changes.** New grilling ticket "Evaluation harness", graduated from the fog. Input posted to "Advice surface UX" (review window), "Positioning decisions" (positions per fight in the replay record) and "Stack and runtime" (offline replay job and replay-record cache). Glossary terms Replay record, Moment, Close call, Follow rate and Evaluation harness added to `CONTEXT.md`.
