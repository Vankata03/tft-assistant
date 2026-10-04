---
id: 1
title: "Map: TFT Assistant MVP spec"
labels: [wayfinder:map]
status: open
assignee:
parent:
blocked_by: []
---

## Destination

An MVP spec for a personal TFT coach, ready to hand to build sessions. The coach reads game state automatically and covers every v1 decision: econ, leveling and rolling, shop buys, transitions and pivots, items, augments, positioning, and carousel and opener choices. It runs in two modes: Baseline mode shows Guides and highlights within Riot's policy as approved apps apply it, and the opt-in Live mode gives advice computed from the live game. Output appears in an overlay, on a second screen and as voice callouts, and a post-game review replays each finished game against the engine. Success is measured as average placement over 50 games without the coach, then 50 games in Live mode.

## Notes

- **Domain**: Teamfight Tactics (Riot Games). Glossary in [`CONTEXT.md`](../CONTEXT.md). Vault project: `C:/Vault/10 Projects/TFT Assistant/`.
- **Skills**: grilling tickets call `grilling` and `domain-modeling`. Research tickets call `research` and commit findings on a `research/<slug>` branch. Update `CONTEXT.md` whenever a term is settled.
- **Audience**: personal tool first, designed so it can go public later. Public release is not a requirement.
- **Policy**: settled in [Policy stance and feature modes](008-policy-stance-and-modes.md). Baseline mode follows Riot's third-party policy as approved apps apply it. Live mode breaks it and runs on the owner's main account at the owner's risk. Live mode is a separable component a public build can omit. The coach never automates input.
- **Game-state input**: automatic capture only. Manual entry is rejected.
- **Advice engine**: settled in [Advice engine architecture](011-advice-engine-architecture.md).
- **Data**: settled in [Data source strategy](010-data-source-strategy.md).
- **Hardware** (owner's PC, checked 2026-10-04): AMD Ryzen 7 7800X3D, 32 GB RAM, AMD Radeon RX 6800 (16 GB VRAM, no CUDA). Any local model shares this GPU with the running game.

## Decisions so far

<!-- one line per closed ticket: [title](link): gist -->

- [Current TFT set and its mechanics, including wisp](005-current-set-mechanics.md): Set 18 (Enchanted Wilds, patch 18.3); the Wisp is a per-round shop purchase that changes econ, XP and roll odds, and its tables change every patch.
- [Automatic game-state capture options for TFT](003-game-state-capture-options.md): Overwolf game events cover almost all state (needs Overwolf developer access; augment keys forbidden); screen capture is the only Overwolf-free route; Riot's port 2999 API is unusable for TFT; memory reading is blocked by Vanguard.
- [Riot third-party app policy for real-time TFT advice](002-riot-third-party-policy.md): real-time prescriptive advice (level, roll, buy) is forbidden on every surface with no personal-tool exemption, so the opt-in mode risks the account; pre-game guides, comp-unit highlighting, stage-keyed leveling and post-game review are allowed; from 2026-10-06 Vanguard blocks memory access for unknown apps.
- [TFT stats data sources and their APIs](004-stats-data-sources-and-apis.md): only Riot has a documented API (match results, no positions or round-by-round econ); MetaTFT, tactics.tools and TFT Academy serve undocumented, unlicensed JSON; self-aggregation needs about 12.5k matches per patch for comp stats and far more for augments.
- [Prior art for TFT decision engines and the train-vs-LLM question](007-decision-engine-prior-art.md): no trained decision model is needed; a deterministic engine (rules, maths, statistics) leads, a local LLM (Vulkan only on the RX 6800) is at most a phrasing layer, and training belongs in screen-capture recognition if that route is chosen.
- [TFT econ, level and roll math and established theory](006-econ-level-roll-theory.md): odds, pool, XP, gold and damage numbers are published in Riot data and patch notes, and hit odds, the XP/gold calendar and level-versus-roll trade-offs are directly calculable; leveling lines and pivot reasoning are heuristics; board strength and pivot timing need statistics.
- [Policy stance and feature modes](008-policy-stance-and-modes.md): Live mode (advice from live state, all opponent data the route gives) is the product, on the main account at the owner's risk; Baseline mode is the same engine filtered to Guides, highlights and grey-zone hints; surfaces share the rules; post-game review joins v1; measured as 50 no-coach games, then 50 Live-mode games.
- [Data source strategy](010-data-source-strategy.md): MetaTFT JSON for statistics with tactics.tools as fallback, TFT Academy for Guides with an owner override file, Data Dragon and CommunityDragon for static data plus a hand-kept per-patch file; refreshed between games, never during one; Diamond+ filter; no Riot crawler in v1, and a personal key for the owner's own matches.
- [Advice engine architecture](011-advice-engine-architecture.md): a deterministic Engine, a pure function of snapshot and history, with a Game plan layer over per-decision sub-engines; optimizes expected placement, simulates Lines only for econ, level and roll, CPU only, no trained model and no LLM in v1; the Live advisor is the separable Live-mode part.
- [Transition and pivot domain model](012-transition-and-pivot-model.md): the Game plan is folded from history, Open then Committed with a Backup comp; comps are compared by comp fit (expected placement) summed from sub-engine fit terms; a pivot needs a per-stage margin and reverts if the player does not follow; transition is strength-gated with the roll-down as deadline; contest acts only through hit odds.
- [Register a Riot personal API key](017-register-riot-personal-api-key.md): personal key submitted and pending review; a 24-hour development key in `$HOME\.config\tft-assistant\riot-api-key` serves until then; app limit 20/s and 100/2 min; account, match, summoner and league endpoints all answer for the owner's EUNE account, which has 100+ matches.
- [Record the pre-coach baseline](016-record-pre-coach-baseline.md): rolling baseline of the last 50 no-coach ranked games from the same set as the Live-mode games, refreshed before the first Live-mode game; the 2026-10-04 snapshot is 4.62 average placement at Platinum III; the match API no longer reports the patch.
- [Econ, level and roll Line simulation](018-econ-level-roll-line-simulation.md): seeded Monte Carlo with common random numbers over about 7 candidate Lines to the end of the next stage; roll depth emerges from gold floors, with no HP table and no deliberate loss streak; a Line margin damps flips; the player can pin a Line in Live mode; the simulated placement is the backbone of comp fit for the target, Backup and top challengers, and other comps are screened analytically.

## Not yet specified

- **Advice surface UX**: what each surface (overlay, second screen, voice) shows, the latency budget per game phase, and how a callout competes with the player's attention. Needs the capture route first; mode rules per surface are settled in "Policy stance and feature modes". The owner wants the coach graphical and interactive, not only text: in Live mode the econ advice carries a per-Line projection to draw and lets the player pin a Line ("Econ, level and roll Line simulation"), so the surfaces need a way to show and pick Lines within a planning phase.
- **Evaluation harness**: how to judge advice quality before 50 live games. The Engine is a pure function, so recorded games replay through it deterministically; still open is what the replay is compared against (high-elo decisions, outcomes), starting with board and lobby strength. May be answered by "Post-game review scope". Pivot margins, comp fit weights, the Line margin, the terminal HP weight and the opponent growth curve are tuned against it.
- **Patch cadence**: TFT patches every two weeks and a new set roughly every four months. Data refresh is settled in "Data source strategy". Engine numbers and thresholds live in a per-patch tunables file ("Advice engine architecture"). Still open: who fills the static and tunables files on patch day and how, how the owner's overrides survive a patch, and what a new set breaks. The match API's `game_version` no longer names the patch ("Record the pre-coach baseline"), so anything keyed on patch has to map game dates to the patch calendar.
- **Stack and runtime**: language, packaging, and how the capture, engine and surfaces talk to each other. Follows the capture route decision; the Engine runs on the CPU only.
- **Dedicated TFT client**: Riot's new PC client ships on 2026-10-09 or 2026-11-03. Every capture route needs re-checking once it is live.

## Out of scope

- **Input automation**: the coach never clicks, buys or moves units for the player.
- **LLM phrasing** ([Benchmark local LLM inference beside a live TFT game](014-benchmark-local-llm.md)): v1 phrases advice and review prose from templates, so no local language model runs; revisit after v1.
- **Public release and monetization**: a separate effort if the personal tool proves itself.
