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
- **Advice engine**: the owner doubts a cloud LLM is the answer. Training a model, a local LLM and a deterministic solver are all still open.
- **Data**: the owner believes some stats sites expose APIs. Check before choosing scraping or self-aggregation.
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

## Not yet specified

- **Advice surface UX**: what each surface (overlay, second screen, voice) shows, the latency budget per game phase, and how a callout competes with the player's attention. Needs the capture route first; mode rules per surface are settled in "Policy stance and feature modes".
- **Evaluation harness**: how to judge advice quality before 50 live games, for example replaying recorded games or comparing against high-elo decisions. Depends on the data available, and may be answered by "Post-game review scope".
- **Sub-engines for items, augments, positioning and carousel**: each probably needs its own model of the decision. These become tickets once the engine architecture is chosen.
- **Patch cadence**: TFT patches every two weeks and a new set roughly every four months. How the coach refreshes its data and rules per patch and per set.
- **Stack and runtime**: language, packaging, and how the capture, engine and surfaces talk to each other. Follows the capture route and engine decisions.
- **Dedicated TFT client**: Riot's new PC client ships on 2026-10-09 or 2026-11-03. Every capture route needs re-checking once it is live.

## Out of scope

- **Input automation**: the coach never clicks, buys or moves units for the player.
- **Public release and monetization**: a separate effort if the personal tool proves itself.
