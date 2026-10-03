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

An MVP spec for a personal TFT coach, ready to hand to build sessions. The coach reads game state automatically and advises on every v1 decision: econ, leveling and rolling, shop buys, transitions and pivots, items, augments, positioning, and carousel and opener choices. Advice is shown in an overlay, on a second screen, and as voice callouts. Success is measured as average placement over 50 games, before and after.

## Notes

- **Domain**: Teamfight Tactics (Riot Games). Glossary in [`CONTEXT.md`](../CONTEXT.md). Vault project: `C:/Vault/10 Projects/TFT Assistant/`.
- **Skills**: grilling tickets call `grilling` and `domain-modeling`. Research tickets call `research` and commit findings on a `research/<slug>` branch. Update `CONTEXT.md` whenever a term is settled.
- **Audience**: personal tool first, designed so it can go public later. Public release is not a requirement.
- **Policy**: the baseline must comply with Riot's third-party app policy. Real-time advice that the policy forbids is an opt-in mode the owner runs at their own risk. The coach never automates input.
- **Game-state input**: automatic capture only. Manual entry is rejected.
- **Advice engine**: the owner doubts a cloud LLM is the answer. Training a model, a local LLM and a deterministic solver are all still open.
- **Data**: the owner believes some stats sites expose APIs. Check before choosing scraping or self-aggregation.
- **Hardware** (owner's PC, checked 2026-10-04): AMD Ryzen 7 7800X3D, 32 GB RAM, AMD Radeon RX 6800 (16 GB VRAM, no CUDA). Any local model shares this GPU with the running game.

## Decisions so far

<!-- one line per closed ticket: [title](link): gist -->

## Not yet specified

- **Advice surface UX**: what each surface (overlay, second screen, voice) shows, the latency budget per game phase, and how a callout competes with the player's attention. Needs the capture route and the policy stance first.
- **Evaluation harness**: how to judge advice quality before 50 live games, for example replaying recorded games or comparing against high-elo decisions. Depends on the data available.
- **Sub-engines for items, augments, positioning and carousel**: each probably needs its own model of the decision. These become tickets once the engine architecture is chosen.
- **Patch cadence**: TFT patches every two weeks and a new set roughly every four months. How the coach refreshes its data and rules per patch and per set.
- **Stack and runtime**: language, packaging, and how the capture, engine and surfaces talk to each other. Follows the capture route and engine decisions.
- **Baseline measurement**: the owner's current rank and average placement over recent games, recorded before the coach is used.

## Out of scope

- **Input automation**: the coach never clicks, buys or moves units for the player.
- **Public release and monetization**: a separate effort if the personal tool proves itself.
