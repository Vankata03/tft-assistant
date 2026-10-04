# TFT Assistant: MVP spec

This is the build spec for v1 of the coach. It compiles the decisions recorded on the wayfinder map, [TFT Assistant MVP spec](../issues/001-map-tft-assistant-mvp-spec.md), and makes no new ones. Every statement traces to a closed ticket, and each section links the tickets it draws on. Where a ticket holds more detail than the spec, the ticket wins.

Terms follow the glossary in [`CONTEXT.md`](../CONTEXT.md). Capitalised or domain terms such as Engine, Line, Comp fit, Board power, Snapshot and Game log mean exactly what the glossary says.

Status: compiled 2026-10-04 for patch 18.3 of Set 18 (Enchanted Wilds) and read by the owner, who accepted the build order. Two gaps are open as tickets; see [Open items](#open-items).

## Contents

| Part | File |
| --- | --- |
| Purpose, success measure, modes and policy, architecture, build order, out of scope, open items | this file |
| Game-state capture | [spec/capture.md](spec/capture.md) |
| Data sources, refresh and the Riot API | [spec/data.md](spec/data.md) |
| The Engine: contract, Game plan, transitions and pivots, board power | [spec/engine.md](spec/engine.md) |
| Sub-engines: econ, level and roll Lines; items; augments; shop, Wisp and carousel; positioning | [spec/sub-engines.md](spec/sub-engines.md) |
| Advice surfaces: overlay, second screen, voice | [spec/surfaces.md](spec/surfaces.md) |
| Game log, post-game review and evaluation harness | [spec/review-and-harness.md](spec/review-and-harness.md) |
| Stack, runtime, storage and repository layout | [spec/runtime.md](spec/runtime.md) |
| Patch-day and new-set workflow | [spec/patch-workflow.md](spec/patch-workflow.md) |
| Tunables index | [spec/tunables.md](spec/tunables.md) |

## Purpose and success measure

Sources: the map's Destination, [Policy stance and feature modes](../issues/008-policy-stance-and-modes.md), [Record the pre-coach baseline](../issues/016-record-pre-coach-baseline.md), [Patch-day and new-set workflow](../issues/028-patch-day-and-new-set-workflow.md).

The coach is a personal Teamfight Tactics coach for its owner. It reads game state automatically, by screen capture and the League client API, and never through manual entry. It covers every v1 decision: econ, leveling and rolling, shop buys, transitions and pivots, items, augments, positioning, the Wisp, and carousel and opener choices. Output appears in an overlay, on a second screen and as voice callouts. A post-game review replays each finished game against the Engine. The coach never automates input: it never clicks, buys or moves units.

It is a personal tool first, designed so it could go public later. Public release is not a requirement.

**Success measure.** Average placement over 50 ranked games without the coach (the pre-coach baseline), then over 50 games in Live mode with post-game review on.

- The pre-coach baseline is rolling: the last 50 ranked games (queue `1100`) of the same set as the Live-mode games, played without the coach or as silent games. It is refreshed just before the first Live-mode game. If the set has fewer than 50 such games by then, the owner plays the missing ones first.
- The snapshot taken on 2026-10-04 is 4.62 average placement (standard deviation 2.49, standard error 0.35) at Platinum III. The difference between two 50-game averages has a standard error of about 0.5, so only a large improvement will stand out.
- The 50 Live-mode games must finish within Set 18. If they cannot, the run restarts in the new set with a fresh pre-coach baseline. Set 19 is expected around 2026-12-01 ([Current TFT set and its mechanics, including wisp](../issues/005-current-set-mechanics.md)).
- No evaluation gate ever uses the placement of the 50 Live-mode games ([Evaluation harness](../issues/027-evaluation-harness.md)).

## Modes and policy

Sources: [Riot third-party app policy for real-time TFT advice](../issues/002-riot-third-party-policy.md), [Policy stance and feature modes](../issues/008-policy-stance-and-modes.md), [Advice engine architecture](../issues/011-advice-engine-architecture.md), [Stack and runtime](../issues/025-stack-and-runtime.md).

Riot's policy forbids real-time prescriptive advice ("level now", "roll", "buy this") on every surface, with no exemption for a personal tool. It allows static Guides chosen before the game, highlighting the chosen comp's units in the shop, stage-keyed leveling guidance, and post-game analysis. It bans tracking opponents during play. Riot has said nothing about screen capture.

The coach therefore has two modes over one Engine:

- **Live mode** is the product. It gives advice computed from the live game state, including whatever the capture route knows of opponents' boards. It runs on the owner's main account; the owner accepts the Terms of Service risk. It is opt-in: one switch per session, off by default.
- **Baseline mode** shows Guides, shop highlights and a few grey-zone hints, never advice computed from the live game state. It is compliant by the precedent of approved apps, not provably compliant. Its grey-zone hints are an XP-aware leveling hint, par win chance and the list of opponents already faced (names and results only).

Opponent-board data is Live mode only during a game, with no exception ([Baseline mode and opponent sightings](../issues/031-baseline-mode-and-opponent-sightings.md)):

- Capture and the game log are the same in every mode, so Baseline mode logs raw sightings (trait rows, unit counts, hidden-row count, level). It never infers a board from them and never shows them during the game. Post-game review infers boards from the log in both modes.
- Per-opponent win chance is Live mode only during a game. Baseline mode shows **par win chance** instead: `win_probability` of the player's board against the par board, the opponent growth curve's board power for the round. It uses no opponent data and is a number only, never an action.
- The **XP-aware leveling hint** states the gap between the player's level and XP and the Guide's stage-keyed level target, counting passive XP up to the target round, for example "Guide: 8 at 4-2 · 3 XP buys (12 gold) short". It is a fact, never "level now", and is plain arithmetic over the static XP table.
- During a game in Baseline mode, the advice pipeline (Game plan, sub-engines, Line simulator, opponent model) never runs. Baseline features may call only an allowlist of Engine functions: own-board board power, `win_probability` and the opponent growth curve lookup ([spec/engine.md](spec/engine.md#mode-separation)). Offline per-patch output, such as the Wisp worth table, counts as static data.

Silent games are a third way to run a session: the coach captures and logs the game and shows nothing ([Evaluation harness](../issues/027-evaluation-harness.md)). How a session is set to silent is open ([Data refresh trigger and silent sessions](../issues/033-data-refresh-trigger-and-silent-sessions.md)).

What each mode shows per decision:

| Decision | Baseline mode | Live mode |
| --- | --- | --- |
| Comp choice | Picker sorted by meta tier, chosen by the player before or during the game, not filtered by the board | Game plan from the opener, items and augments |
| Econ | Static stage plan from the comp's Guide | Save or spend calls from gold, HP and streak |
| Level and roll | Stage-keyed level and roll plan from the Guide, plus the XP-aware leveling hint | "Level now", "Roll to N gold", hit odds, Line projection and pinning |
| Shop | Display-only highlight of the comp's units | Buy, sell and hold calls |
| Wisp | Offline Wisp worth table per patch | Live buy call |
| Items | Best-in-slot items and recipes, with held components highlighted | Slam, placement, remover and handover calls |
| Augments | Per-comp and global tiers with the Guide tag (no Set 18 statistics exist) | Ranked pick and reroll advice |
| Positioning | The Guide's final and interim layouts | Target layout with live adjustments |
| Carousel and opener | The Guide's carousel priority list | Ranked pick from the board and items |
| Transition | The Guide's interim board and transition stage | "Swap X for Y", "Hold Y", "Sell X" |
| Pivot | Alternatives listed before the game; the player decides | Live pivot call |

Surfaces do not change the rules: Riot judges content, not surface, so the overlay, the second screen and voice follow the same mode rules. In Baseline mode voice reads only the Guide's step for the stage.

Post-game review runs in both modes, because the policy encourages post-game analysis. The Engine core therefore always ships. The separable part of Live mode is the Live advisor, packaged as the `live` Python package plus a UI module. A public build omits both.
## Architecture at a glance

Sources: [Game-state capture route](../issues/009-game-state-capture-route.md), [Advice engine architecture](../issues/011-advice-engine-architecture.md), [Stack and runtime](../issues/025-stack-and-runtime.md), [Post-game review scope](../issues/015-post-game-review-scope.md).

```text
TFT window ──WGC capture──▶ Python core ─────────────────────────────────────────┐
League client API ─phase──▶  capture thread: change checks, OCR, board reader,   │
                             purchase tracking ─▶ Snapshot                        │
                             Engine thread: advise(snapshot, history,             │
                               data snapshot, mode) ─▶ ranked advice list         │
                             game log writer (JSONL + keyframes)                  │
                                   │ JSON over localhost WebSocket               │
                                   ▼                                              │
                             Electron shell: overlay, second screen, voice        │
After the game: review job replays the game log through the Engine ─▶ replay records ─▶ review, harness
Between games: data refresh writes a new immutable data snapshot
```

- Capture turns frames into a Snapshot: every field with its last known value, age and source.
- The Engine is a deterministic pure function, CPU only, budget 100 ms per snapshot. It has a Game plan layer and one sub-engine per decision.
- The Python core and the Electron UI are two processes joined by a versioned JSON WebSocket.
- The game log is the source of truth for review and the evaluation harness. Both read the replay records produced by replaying it through the Engine.

## Build order

The owner accepted this order on 2026-10-04, when closing [Assemble the MVP spec](../issues/029-assemble-mvp-spec.md). It aims to get silent games logging early, because silent games feed the pre-coach baseline and give the evaluation harness game logs before the first Live-mode game.

1. **Skeleton.** The uv workspace (`engine`, `capture`, `live`, `review`, `harness`), the Electron shell that starts and supervises the core, the versioned WebSocket with generated schemas, the tray app and the League client API phase watcher. Exit: the shell starts the core and shows the gameflow phase.
2. **Capture and game log, for silent games.** Name lists from Data Dragon and CommunityDragon for OCR matching, WGC capture with change checks, digit templates and RapidOCR for the HUD, shop, Wisps, augments, carousel, trait panel (own and scouted, with the hidden-row count), player list and scouted players' levels, purchase tracking, fight results, the JSONL game log with keyframes, the SQLite index, crash re-attach, and the silent session. Exit: the owner plays ranked silent games and each leaves a complete game log. From here every ranked game counts toward the refreshed baseline and feeds the harness.
3. **Board reader.** TFT-COACH's reader with the four fixes, and the training-crop pipeline (`tft-train`) fed by the silent-game logs.
4. **Data layer.** The TOML static, tunables and override files with schema and `source` tags, `tft-data new-patch`, `data/patches.toml`, the MetaTFT, tactics.tools and TFT Academy adapters, immutable data snapshots, the refresh job, and the Riot API client (own User-Agent) with the baseline refresh script.
5. **Board power and the first harness metrics.** Unit, trait and item terms, the three global weights fitted on the owner's final boards, the four interface functions, the growth curve, the comp classifier and the opponent model (the inferred-board solver, its priors fitted on match final boards, and `opponent_star_mix`). `tft-harness eval` with final-board ranking now, and `win_probability` and damage calibration from silent-game logs.
6. **Engine core.** Snapshot and history model, the Game plan fold, comp fit, transition and the recommended board, and the Line simulator measured against the 100 ms budget.
7. **Remaining sub-engines.** Shop and bench, Wisp, items, augments, carousel, positioning, each with its required fields and silence rules.
8. **Replay, review and the full harness.** Replay records, the post-game review on the second screen, owner tags, gates, flip rate and `tft-harness fit`.
9. **Baseline mode surfaces.** Guides, highlights, the Wisp worth table, tiers, Guide layouts, Baseline voice and the grey-zone hints.
10. **Live advisor and Live surfaces.** The `live` package, the anchored overlay, the cockpit, voice callouts, Line pinning, roll-down mode and the latency budgets.
11. **Start the run.** Refresh the pre-coach baseline, then play the 50 Live-mode games in blocks of 10.

Slices 3 to 5 can overlap once slice 2 is logging. The calendar is tight: everything must fit before Set 19 (around 2026-12-01) for the measurement to finish within Set 18.

## Out of scope

From the map's Out of scope section:

- **Input automation.** The coach never clicks, buys or moves units for the player.
- **LLM phrasing** ([Benchmark local LLM inference beside a live TFT game](../issues/014-benchmark-local-llm.md)). v1 phrases advice and review prose from templates and runs no language model.
- **Overwolf** ([Game-state capture route](../issues/009-game-state-capture-route.md)). The owner does not apply for Overwolf developer access; the coach reads the screen.
- **Counter-positioning against opponent hexes and items** ([Positioning decisions](../issues/022-positioning-decisions.md)). v1 does not read opponent positions or items.
- **The next set's set mechanic** ([Patch-day and new-set workflow](../issues/028-patch-day-and-new-set-workflow.md)). v1 fixes only the plug-in contract and the repair order.
- **Public release and monetization**, including a real installer. v1 runs from the repository ([Stack and runtime](../issues/025-stack-and-runtime.md)).

Also deferred past v1 by individual tickets: free-form what-if editing of a Line or pick in review ([Post-game review scope](../issues/015-post-game-review-scope.md)), a combat simulator that could score hexes ([Positioning decisions](../issues/022-positioning-decisions.md)), a Riot API crawler for self-aggregated statistics ([Data source strategy](../issues/010-data-source-strategy.md)), a pin hotkey ([Advice surface UX](../issues/026-advice-surface-ux.md)), and reading opponent units on scouted boards ([Benchmark open-source board recognition on probe frames](../issues/024-benchmark-board-recognition.md)).

## Open items

### Gaps raised as tickets

These need a decision no ticket made, or sit between tickets that disagree. Each is a grilling ticket on the map.

- [Families for unassigned tunables](../issues/032-families-for-unassigned-tunables.md). About 20 tunables have an owner but no family; see [spec/tunables.md](spec/tunables.md).
- [Data refresh trigger and silent sessions](../issues/033-data-refresh-trigger-and-silent-sessions.md). Two refresh rules disagree (per-source minimum ages against a flat 6 hours), and no ticket says how a session is set to silent.

### Fog carried from the map

- **Dedicated TFT client.** Riot's new PC client ships on 2026-10-09 or 2026-11-03. Once it is live, re-check the screen-capture route: window title, HUD layout and the overlay anchors that follow it, and the League client API phases. `probe/probe.ps1` re-runs the client, port 2999 and capture checks. The probe game ran on 2026-10-04, before Vanguard's 2026-10-06 memory-access change; screen capture reads no memory, but the same re-run confirms it.

### Open build facts

Facts the build must check. None needs a decision.

- **Augment statistics.** MetaTFT's `comp_augment_tiers` holds per-comp curated tiers (S, A, B), not statistics, and no source publishes Set 18 augment statistics ([Augment decisions](../issues/021-augment-decisions.md)). The statistics path switches on per augment if a source publishes rows again.
- **End-of-game endpoint.** Whether the League client's `lol-end-of-game/v1/tft-eog-stats` gives final placement and boards faster than the match API, with no key ([Post-game review scope](../issues/015-post-game-review-scope.md)).
- **OCR engine.** Benchmark RapidOCR against Windows.Media.Ocr on the probe frames before the OCR engine is locked ([Stack and runtime](../issues/025-stack-and-runtime.md)).
- **Engine budget.** Measure the 100 ms budget during the build. If the Line simulator misses it, move only its inner loop to a compiled extension. Pick the recommended board by greedy selection with swap improvement, because exhaustive search is near the budget ([Transition and pivot domain model](../issues/012-transition-and-pivot-model.md)).
- **Board reader.** Apply the four fixes and measure the item bench, which the benchmark did not cover ([Benchmark open-source board recognition on probe frames](../issues/024-benchmark-board-recognition.md)).
- **Opponent inference** ([Opponent model from trait-only sightings](../issues/030-opponent-model-from-trait-only-sightings.md)). The combined case of unknown emblems and a trait panel cut to 9 rows was not measured; the harness's inference metric measures it from game logs. Hidden rows were inactive in the one probe game; confirm that the panel always hides inactive rows first.
- **Current opponent per round.** Fight metrics, the opponents-faced list and the "possible next opponents" set all need the opponent fought in each combat round. The probe listed the HUD fields it read, and the current opponent was not among them. Confirm the coach can read it from the screen.
- **Static-file defaults not yet confirmed** ([Probe live game data sources in a real TFT game](../issues/013-probe-live-game-data.md)): PvE orb gold per PvE round, and the damage per surviving enemy unit for Set 18. The local probe frames hold HP and boards for every round if the damage rule needs checking.
- **Riot personal key.** Submitted on 2026-10-04 and pending review. Until approved, a 24-hour development key in `$HOME\.config\tft-assistant\riot-api-key` serves, regenerated on days the owner plays ([Register a Riot personal API key](../issues/017-register-riot-personal-api-key.md)).
- **Overlay hotkey.** The default key that toggles the whole overlay is left to the build ([Advice surface UX](../issues/026-advice-surface-ux.md)).
