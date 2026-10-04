# Game log, post-game review and evaluation harness

Part of the [MVP spec](../spec.md). Sources: [Game-state capture route](../../issues/009-game-state-capture-route.md), [Post-game review scope](../../issues/015-post-game-review-scope.md), [Evaluation harness](../../issues/027-evaluation-harness.md), [Stack and runtime](../../issues/025-stack-and-runtime.md), [Board and lobby strength heuristic](../../issues/019-board-and-lobby-strength-heuristic.md), [Positioning decisions](../../issues/022-positioning-decisions.md), [Advice surface UX](../../issues/026-advice-surface-ux.md), [Record the pre-coach baseline](../../issues/016-record-pre-coach-baseline.md), [Opponent model from trait-only sightings](../../issues/030-opponent-model-from-trait-only-sightings.md).

## Game log

The game log is the coach's record of one game and the source of truth for review and the harness.

- **Key.** The League client API's game id.
- **Structured content**, kept forever: every snapshot with each field's timestamp and source; every offer, roll, pick, sighting and fight result (opponent fought, result, HP lost); the own board's hexes at the last snapshot before each combat; every piece of advice shown, with timestamp and surface (reported by the UI); every disagreement between the board reader and purchase tracking; capture gaps from crashes and core restarts; stale-field silences; the data snapshot's patch label; the board-reader model version; and a flag for games played on the previous patch's static file.
- **Format.** One append-only JSON Lines file per game, which survives a crash mid-write and replays in order.
- **Media** is a setting. Keyframes by default (each shop after a roll; each augment, Wisp and carousel offer; each scouted board; the end of each planning phase), stored as lossless WebP beside the log, roughly 100 to 300 MB per game. Full video is the alternative. Media is capped at 20 GB with the oldest deleted first; the 50 Live-mode evaluation games are pinned. Lossless frames at the probe's rate would cost about 6 GB per game.
- **Index.** A SQLite index across games holds game id, date, patch, placement, the pinned flag, each Live-mode game's 10-game block and engine version, and the replay-record cache. It can always be rebuilt from the logs.
- Augments come only from the game log, because the Riot match record for Set 18 has none. A game without a log gets no review.

## Replay records

Replaying a game log through the Engine yields a replay record for every decision point: the snapshot, the player's choice, the Engine's choice, every option the Engine scored, the estimated cost and the shown-advice status. Post-game review and the evaluation harness both read replay records. The review does not double as the harness.

## Post-game review

### Data and timing

- **Sources.** The game log is required. The Riot match API adds the final placement, the elimination order and all eight final boards (units, stars, items, traits). The League client's `lol-end-of-game/v1/tft-eog-stats` endpoint is checked during the build as a faster source that needs no key.
- **When.** The review is computed as a subprocess at below-normal CPU priority when the League client reports the end of the game. About 300 decision points at the 100 ms budget take about 30 s. A "Review ready" toast appears; the player opens the review in the second-screen window on demand. If the next game starts first, the review keeps running at low priority.
- **Versioning.** Each review is stored with the engine version and the data snapshot id. It is regenerated on demand with the current engine and that game's own data snapshot, so engine fixes show on old games while the patch data stays correct.

### Cost and moments

- **Coverage.** Every decision point is replayed, because slow leaks (interest lost over many rounds, bench mis-sells) show only when summed.
- **Cost** of a decision is the Engine's expected placement for its own choice minus its expected placement for the player's choice, judged with only the information available at that moment, never with hindsight. The player's actual Line is inferred from level-ups and roll-downs and simulated as an extra candidate Line with the same seed. A pinned Line is judged against the recommended Line.
- A decision whose sub-engine gives no placement value (shop buys use board power gain, carousel picks use a ranked list) is marked "differed" with no cost and ranks below costed decisions. Positioning is never a moment.
- Outcome facts, such as a fight result or whether the key units were hit, are context and never enter the cost.
- **Close calls.** A gap below `review_min_cost` (default: the larger of the estimate's standard error and 0.05 placement) never enters the top moments but stays on the timeline.
- **Grouping.** The same deviation at consecutive decision points (no level-up for three rounds, the same component held for four rounds) merges into one moment with the summed cost.
- **Shown-advice status**, one per moment: the coach said X and the player did Y (ignored); the coach was silent but would have said X (capture gap); the player followed the advice and it still cost (Engine error); or "no advice in Baseline mode".
- **Follow rate** is the share of shown advice the player followed in a game.
- **Summing.** Per-decision deltas compound and overlap, so per-category sums are labelled "estimated", and the review never claims a counterfactual placement such as "you would have placed 2nd".

### Layout

- **Game summary** at the top: placement, estimated cost per category and follow rate; a Game plan timeline (candidate and target comps by round, the commit point, pivots called and taken, called and ignored, and taken without a call); a Line chart (the player's actual Line against the recommended Line and any pinned Line, as level and gold by round); a fight strip (win chance against result, and predicted against actual HP lost per combat round); and a debug tab (capture gaps, stale-field silences, and board-reader disagreements with keyframes).
- **Top 5 moments** by estimated cost, as cards: the round, the category (econ, level and roll; shop; Wisp; items; augments; carousel; transition; pivot), what the player did, what the Engine chose, the estimated cost, a template reason (the top two fit terms, or the Line projection difference in gold, level, hit probability and expected HP), the shown-advice status and the keyframe. Each card expands to the options the Engine scored.
- **What-if.** At each moment the player can pick any option the Engine already scored and see its estimate, with no new simulation.
- **Owner tags.** Each moment card carries an agree, disagree or unsure tag. Tags live in the review store, keyed by game and decision point, never in the game log, and survive regeneration.
- **Positioning notes**, one per fight: whether a layout was advised and followed, and the result against win chance.
- **Full timeline**, round by round, below the moments. Decisions inside a crash gap are not reviewed; the timeline shows the gap.
- **Cross-game view.** A game list (date, mode, placement, total estimated cost, worst category), plus average cost per category over the last 10 games and over the 50-game Live-mode run. Match-API baseline games appear with placement only.
- Baseline-mode games get the same full review.

## Evaluation harness

The evaluation harness judges the Engine's advice quality across many game logs and proposes tunables. It is a manual CLI, never scheduled, with no second-screen view.

### What it judges

- **Primary: predictions against outcomes.** At every decision point the Engine makes checkable predictions: `win_probability` per fight, damage per lost round, the probability of hitting the key units by a gold floor, the Line projection (gold, level and HP at the horizon), the expected placement and each opponent's inferred board (against their final board from the match API, for opponents scouted in their last stage alive). The harness scores each against what happened. A game gives about 300 decision points and about 20 fights.
- **Change guard: advice diff.** The share of decision points whose advice changed between the accepted version and a candidate, with the largest changes listed.
- **Report-only:** placement after followed against ignored advice (confounded, standard error about 0.5 placement over 50 games); the owner's disagree rate; calibration curves by stage; expected placement split by follow rate; the positioning residual (`win_probability` residual on fights where anti-dive or anti-AoE was active, split by followed and not followed); late and too-late advice shares per kind; and the capture gap share.
- No source publishes round-by-round decisions of high-elo players, so comparing against them is not possible in v1. No gate uses the placement of the 50 Live-mode games.

### Gates

Each fitted metric has two comparative gates and no absolute threshold:

- **Beat a naive baseline.** `win_probability` beats a stage-only win rate on Brier score. Expected placement beats the HP rank on mean absolute error. Hit probability beats the closed-form shop chain on log-loss. Damage beats the stage base alone on mean absolute error. The sighting age weight and persistence boost beat a model with no persistence on the log-loss of each opponent's next sighting.
- **No regression.** A candidate is not worse than the accepted version by more than the 95 % bootstrap interval, resampled by game.
- **Flip rate.** A flip is advice A, then B, then A within 3 planning phases with no change in the sub-engine's required fields that explains it. The rate per sub-engine must not rise against the accepted version. Target, not a gate: under 5 % of decision points.

Absolute thresholds may be added after 20 logged games, if the curves suggest them.

### Tunable families

Only family 1 is tuned on the owner's games, which is the main guard against overfitting. The index of every tunable is in [tunables.md](tunables.md).

1. **Fitted** on game logs by maximum likelihood (log-loss or mean absolute error) and gated.
2. **Margins**, set from noise (including `transition_tolerance`): each margin is z times the standard error of the difference it guards, combining Monte Carlo noise and the model error measured for family 1, per decision kind and stage. z is 2 for costly or sticky calls (pivots, comp-defining augments) and 1 for cheap or reversible ones. The harness writes each margin to the tunables file as a fixed number per stage; the Engine never computes margins live. Current starting values stay as floors until the harness has data.
3. **Priors from public statistics**, set by empirical Bayes or holdout on MetaTFT and tactics.tools data.

A fourth group is hand-set and report-only, because no v1 data can set it. A fifth is computed from data at each refresh (`opponent_growth_curve`, `default_lines_by_carry_cost`).

### Checks on hand-set tunables

Each check is report-only, never a gate.

- **Widened-candidate check.** Replay with a widened candidate set, where the 100 ms budget does not apply: gold floors every 10 gold, `all_in_rounds_left` and `stabilize_rounds_left` removed, and `line_candidate_cap`, `challengers_simulated`, `slam_candidate_cap` and `open_candidate_count` raised. Report how often the chosen advice changes and the expected-placement difference.
- **Classifier.** The label at each stage against the label of the same player's final board: the owner's from the game log, opponents' from the match API.
- **Confidence bands.** Prediction accuracy per confidence band, which must improve from low to medium to high.
- **Board-reader identity.** Where the board reader and purchase tracking disagree, which source the match API's final board proves right, per reader-confidence bucket.
- **Field age.** The stale-silence share per field, inside the capture-gap report.

### Fit protocol

- Games are held out by time: a fit uses the older games and is scored on the newest 20 %.
- Per-stage parameters start pooled across stages; a stage gets its own value only past about 150 fights at that stage, shrunk toward the pooled value.
- Every refit is a candidate that must pass the gates on the holdout.
- During the 50 Live-mode games, tunables are retuned only between blocks of 10 games, and only family 1 is refitted. Margins change mid-run only if the flip rate shows a bug.

### Capture gaps

Data is dropped per decision point and per field, never imputed. A fight with an unknown result leaves the fight metrics; a snapshot inside a crash gap leaves every metric; a stale-field silence counts as a gap. A game with more than 25 % of its rounds in gaps is marked partial: it stays in the fight, damage and hit metrics but leaves expected-placement calibration. Every report states the gap share.

### Commands

- `uv run tft-harness eval` replays every game log (reusing cached replay records unless the engine version or tunables changed) and writes a Markdown report beside the logs: gates, curves, the advice diff, flip rates and the gap share, always against the latest committed tunables file.
- `uv run tft-harness fit` writes a candidate tunables file. The owner accepts it by committing it to `data/`. Git is the record; there is no separate registry.
- `uv run tft-harness fit --priors` recomputes the family 3 priors.

## Silent games

A silent game is captured and logged while the coach shows nothing: no advice, no Guides, no highlights, no voice. Its review stays closed until the Live-mode run starts. It counts as a no-coach game for the pre-coach baseline as long as the owner opens no review of it before then. Silent games feed family 1 fits and calibration before the first Live-mode game, so the refreshed baseline also comes with game logs.

Data available before any game log exists: the owner's 100+ final boards (board power fit), public statistics (family 3) and the probe frames.

How a session is set to silent, and how a silent game is flagged, is open: [Data refresh trigger and silent sessions](../../issues/033-data-refresh-trigger-and-silent-sessions.md).
