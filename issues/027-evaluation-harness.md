---
id: 27
title: "Evaluation harness"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: []
---

## Question

How is the Engine's advice quality judged before and during the 50 Live-mode games, and how are its tunables set against that judgement? "Post-game review scope" settled that replaying a game log through the Engine produces a replay record per decision point, and that the evaluation harness is a separate consumer of those records, re-run over every game log whenever the engine or the tunables change.

Decide:

- What the replay records are compared against: actual outcomes (fights, damage, placement), high-elo decisions from any available source, or the Engine's own consistency across versions.
- Which metrics the harness reports and their pass thresholds. Board power's metrics are already settled in "Board and lobby strength heuristic": final-board ranking (Spearman correlation and placement MAE) now; Brier score, log-loss and calibration by stage of `win_probability`, and damage MAE per lost round, once game logs exist.
- How each tunable is tuned and how overfitting to the owner's few games is avoided. Tunables waiting on this: pivot margins, comp fit weights, the Line margin, the terminal HP weight, the opponent growth curve, the item tunables (class prior strength, component discount), the augment tunables (tier-to-delta map, comp-defining margin), the shop and Wisp tunables (board power buy minimum, Wisp buy margin) and `review_min_cost`.
- What data the harness can use before the coach's own game logs exist, and how it treats games with capture gaps.

## Comments

### 2026-10-04 — claude-code

Input from "Positioning decisions": positioning is rule-based and has no placement cost, so it never produces a moment. The harness reports the `win_probability` residual on fights where an anti-dive or anti-AoE adjustment was active, split by whether the player followed the target layout. The metric is report-only, never a pass gate. Tunables waiting on this ticket: `threat_share_on` (about 0.5), `threat_share_off` (about 0.3) and `board_settle_seconds` (about 2).

### 2026-10-04 — claude-code

Input from "Stack and runtime": the harness is a manual Python CLI (`uv run tft-harness ...`), never scheduled. Game logs are append-only JSON Lines files with lossless WebP keyframes beside them, under `%LOCALAPPDATA%\tft-assistant\`. A rebuildable SQLite index holds game id, date, patch, placement, the pinned flag and the replay-record cache. The engine version is the git commit plus a dirty flag, and replay records cached under a dirty version are never reused. The static and tunables files are TOML in the repo's `data/`, one per patch, so git history records which tunables each run used. Each game keeps the data snapshot it started with.

### 2026-10-04 — claude-code

Input from "Advice surface UX": each kind of advice has a latency budget, from 0.25 s for roll-down shop buys to 3 s for the carousel pick. Advice that misses its budget still shows and is logged as late; advice whose decision passed before it was ready is dropped and logged as too late, and counts as not shown. The harness can report the share of late and too-late advice per kind as a report-only metric. Roll-down mode's thresholds (two rolls within about 2 s to start, about 3 s without a roll to end) are UX settings, not Engine tunables.

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: the inputs above, "Post-game review scope", "Board and lobby strength heuristic", "Econ, level and roll Line simulation", "Transition and pivot domain model", "Item decisions", "Augment decisions", "Shop, Wisp and carousel decisions", "Positioning decisions", "Record the pre-coach baseline" and "TFT stats data sources and their APIs".

Fact checked for this ticket: no source publishes round-by-round decisions of high-elo players. The Riot match record holds final boards only, and MetaTFT's round data from its Overwolf app is not exposed. Comparing the Engine against high-elo decisions is not possible in v1.

- **What replay records are judged against.**
  - **Primary: predictions against outcomes.** The Engine makes checkable predictions at every decision point: `win_probability` for each fight, the damage of each lost round, the probability of hitting the key units by a gold floor, the Line projection (gold, level and HP at the horizon) and the expected placement at each snapshot. The harness scores each against what happened. These are the models every decision rests on, and a game yields about 300 decision points and about 20 fights, so data grows quickly even from few games.
  - **Change guard: advice diff across versions.** The share of decision points whose advice changed between the accepted version and a candidate, with the largest changes listed for inspection.
  - **Report-only:** placement after followed against ignored advice (confounded, and 50 games give a standard error of about 0.5 placement), and the owner's agree, disagree or unsure tags on review moments (a Platinum player's judgement is weak truth, but it catches obvious bugs).
  - No gate ever uses the placement of the 50 Live-mode games.
- **Pass gates.** Each fitted metric has two comparative gates and no absolute threshold:
  - **Beat a naive baseline.** `win_probability` beats a stage-only win rate on Brier score. Expected placement beats the HP rank on mean absolute error. Hit probability beats the closed-form shop chain on log-loss. Damage beats the stage base alone on mean absolute error.
  - **No regression.** A candidate is not worse than the accepted version by more than the 95 % bootstrap interval, resampled by game.
  - Absolute thresholds may be added after 20 logged games, if the curves suggest them.
  - Report-only: calibration curves by stage, expected placement split by follow rate, the positioning residuals from "Positioning decisions", the late and too-late advice shares from "Advice surface UX", the owner's disagree rate, the advice diff and the capture gap share.
- **Three tunable families.** Only the first is tuned on the owner's games, which is the main guard against overfitting to them.
  1. **Fitted** on game logs by maximum likelihood (log-loss or mean absolute error), and gated: `win_scale_by_stage`, `survivor_scale_by_stage`, `terminal_hp_weight`, the board power weights (`unit_weight`, `trait_weight`, `item_weight`) and fight scale, and the correction of `opponent_growth_curve` against sightings. Comp fit has no free weights (it is simulated placement plus item fit plus augment fit); expected-placement calibration checks it, with nothing to fit.
  2. **Margins**, set from noise: pivot margins and the re-raise extra, `line_margin`, `wisp_buy_margin`, `board_power_buy_min`, `comp_defining_margin`, `review_min_cost`, `threat_share_on` and `threat_share_off`. Each margin is z times the standard error of the difference it guards, combining Monte Carlo noise and the model error measured for family 1, per decision kind and stage. z is 2 for costly or sticky calls (pivots, comp-defining augments) and 1 for cheap or reversible ones (Line, Wisp buy, shop buy, `review_min_cost`). The harness writes each margin to the tunables file as a fixed number per stage; the Engine never computes margins live. The current starting values (pivot margin about 0.5 at stage 3 and 0.8 after the roll-down, line margin about 0.1) stay as floors until the harness has data.
  3. **Priors from public statistics**, set by empirical Bayes or holdout on the MetaTFT and tactics.tools data itself: `item_class_prior`, `item_prior_strength`, `unit_prior_strength`, `cost_star_baseline`, and `augment_prior_strength` once augment statistics return.
  - **Hand-set, report only**, because no v1 data can set them: `augment_tier_delta` (MetaTFT's map until Set 18 augment statistics exist), `component_discount_by_stage`, `component_income_by_stage`, `board_settle_seconds`, `open_candidate_temperature`, and the rollout and candidate caps, which the 100 ms budget sets rather than advice quality.
- **Fit protocol for family 1.** Games are held out by time: a fit uses the older games and is scored on the newest 20 %, so it never sees its test games. Per-stage parameters start pooled across stages; a stage gets its own value only past about 150 fights at that stage, shrunk toward the pooled value. Every refit is a candidate that must pass the gates on the holdout.
- **Flip rate.** A flip is advice A, then B, then A again within 3 planning phases, with no change in the sub-engine's required fields that explains it (new shop contents, gold, a fight result or a new sighting each explain a change). The harness reports the flip rate per sub-engine. Gate: the rate does not rise against the accepted version. Target, not a gate: under 5 % of decision points. Family 2 margins are checked against it.
- **During the 50 Live-mode games.** Tunables are retuned only between blocks of 10 games, and only family 1 is refitted. Margins change mid-run only if the flip rate shows a bug. Each game's block is recorded in the game index beside its engine version.
- **Before Live-mode logs exist: silent games.** The coach can capture and log a game while showing nothing: no advice, no Guides, no highlights. Silent games feed family 1 fits and calibration before the first Live-mode game. They count toward the pre-coach baseline as long as the owner opens no review of them before the Live-mode run starts, so the refreshed baseline also comes with game logs. Other data available now: the owner's 100+ final boards (the board power fit already settled), public statistics (family 3) and the probe frames.
- **Capture gaps.** Data is dropped per decision point and per field, never imputed. A fight with an unknown result leaves the fight metrics; a snapshot inside a crash gap leaves every metric; a stale-field silence counts as a capture gap. A game with more than 25 % of its rounds in gaps is marked partial: it stays in the fight, damage and hit metrics but leaves expected-placement calibration, because its final placement depends on rounds the coach did not see. Every report states the gap share.
- **Workflow and output.** `uv run tft-harness eval` replays every game log (with the cache rules from "Stack and runtime") and writes a Markdown report beside the logs: gates, curves, the advice diff, flip rates and the gap share. `uv run tft-harness fit` writes a candidate tunables file. The owner accepts a candidate by committing it to `data/`. The accepted version is the latest committed tunables file, so git is the record and there is no separate registry; every report compares against that commit. The harness has no second-screen view.
- **Owner tags.** Review moment cards on the second screen carry an agree, disagree or unsure tag. Tags live in the review store, keyed by game and decision point, never in the append-only game log, and survive review regeneration. They are report-only.

Glossary terms Silent game and Flip added to `CONTEXT.md`; Pre-coach baseline and Evaluation harness sharpened.

Input posted to "Record the pre-coach baseline" (silent games count), "Advice surface UX" (owner tags on moment cards) and "Stack and runtime" (harness commands and report).
