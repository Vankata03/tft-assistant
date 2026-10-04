---
id: 33
title: "Data refresh trigger and silent sessions"
labels: [wayfinder:grilling]
status: closed
assignee: claude-code
parent: 1
blocked_by: []
---

## Question

Two small gaps found while assembling the spec:

1. **Refresh trigger.** "Data source strategy" refreshes at app start and between games and pulls each source once it is past its own minimum age: 1 hour for statistics, 6 hours for Guides, and on patch change for static data. "Stack and runtime" runs the refresh at core start and on the lobby or end-of-game phase "if the data is older than 6 hours". Decide which rule governs, for example whether the 6-hour check applies to the whole data snapshot or only to Guides.
2. **Silent sessions.** "Evaluation harness" introduced silent games, which show nothing and keep their review closed until the Live-mode run starts. "Policy stance and feature modes" gives the owner's build one Live mode switch per session, off by default. Decide how the owner puts a session into silent mode (for example a three-way session mode: silent, Baseline, Live), how a silent game is flagged in the game log and the game index, and how the review lock is lifted when the Live-mode run starts.

Raised by "Assemble the MVP spec". On resolution, update `docs/spec/data.md`, `docs/spec/review-and-harness.md`, `docs/spec/runtime.md` and the spec's open items.

## Comments

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. The owner chose Live as the default mode once the Live-mode run starts and accepted the other recommendations.

**Refresh trigger.** The per-source minimum ages from "Data source strategy" govern, and the flat 6-hour gate from "Stack and runtime" is dropped. The triggers are core start, the League client API's `Lobby` phase and the end of a game, never during a game. Every trigger checks each source's update timestamp and patch label and pulls only data that has changed and is past its own minimum age: 1 hour for statistics, 6 hours for Guides, and on patch change for static data. A new data snapshot is written only when something was pulled. A flat gate would hold statistics back on patch day, when they move fastest, and the check itself costs only a few small requests.

**Session mode.** The single Live mode switch becomes a three-way session mode: silent, Baseline or Live.

- **Changes.** The owner sets it from the second-screen window or the tray menu, never from the overlay. During a game the mode can only go down (Live to Baseline to silent), never up: the owner keeps a kill switch for Live mode, and a silent game can never become coached. Each change is a game-log event. A game counts under the highest mode it reached.
- **Default.** Silent until the Live-mode run starts, Live after it. A build without the `live` package defaults to Baseline. This amends "off by default" from "Policy stance and feature modes" for the owner's build. Before the run, a forgotten switch must never coach a game, because that game would be lost to the pre-coach baseline. During the run, a forgotten switch would only waste games, and the account risk is already accepted.
- **Silent display.** The overlay and voice show nothing, and no "Review ready" toast appears. The second screen shows only a status line, such as "Silent game · logging · capture OK", or the stale-field banner, so a dead coach can be told apart from a silent one. The tray icon shows the mode.

**Live-mode run.** An explicit owner action starts it: `uv run tft-harness start-run`. The command refreshes the pre-coach baseline from the match API and freezes it (average placement, game count, rank), records the start time in `run.json` under `$HOME\.config\tft-assistant\`, and unlocks the reviews of silent games played before it. Live-mode games after it are numbered 1 to 50 in 10-game blocks. Live-mode games played before it, for example while building Live mode, are dev games and do not count toward the 50. The run state lives outside the SQLite index, so the index stays rebuildable from the logs plus `run.json`.

**Flags.** The game log records the session mode at game start and every change to it. The index gains the session mode (the highest the game reached) and whether its review is locked.

**Review lock.** The review of a silent game played before the run starts is computed but stays locked until `start-run`, with no override. Silent games played after the run starts get a normal review. Before the run starts, `tft-harness eval` leaves per-decision content for locked games out of its report (advice diff rows and example moments) and keeps the aggregates: calibration curves, gates, flip rates and the gap share. Fits use locked games in full.

**Pre-coach baseline rule.** The last 50 ranked games (queue `1100`) of the set that have either no game log or a game log that stayed silent throughout. A game whose log reached Baseline or Live mode is excluded. Match-API games are joined to game logs by game id (`EUN1_<gameId>` against the League client API's game id), which the build confirms; it is listed as an open build fact. The owner accepted one known leak: what dev Live games teach can still carry into later baseline games, and no rule catches that.

Updated: `docs/spec.md` (Live mode bullet, new Session mode block under Modes and policy, success measure, build order slices 2 and 11, open items: no gap tickets left, new "Game id join" build fact), `docs/spec/data.md`, `docs/spec/runtime.md` (channel, Live mode separation, data refresh, `start-run` command, `run.json`, tray), `docs/spec/review-and-harness.md` (game log, index, commands, Silent games section) and `docs/spec/surfaces.md` (Silent games section). Glossary terms Session mode and Live-mode run added to `CONTEXT.md`; Live mode, Baseline mode, Silent game and Pre-coach baseline sharpened.
