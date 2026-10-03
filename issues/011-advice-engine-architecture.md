---
id: 11
title: "Advice engine architecture"
labels: [wayfinder:grilling]
status: closed
assignee: Ivan Terziev
parent: 1
blocked_by: [3, 4, 6, 7]
---

## Question

What produces the advice: a deterministic solver over statistics, a local LLM, a trained model, or a hybrid? Decide which part of the engine owns which decision, whether any model must be trained, and how the engine fits the owner's hardware alongside the running game.

## Comments

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner. Sources: "Prior art for TFT decision engines and the train-vs-LLM question", "TFT econ, level and roll math and established theory", "Policy stance and feature modes" and "Data source strategy".

- **Decision maker.** A deterministic Engine decides all advice: rules, game maths (hit odds as a Markov chain over shops, the XP and gold calendar, the damage model and rounds left to live), statistics and Guides. No trained model and no LLM makes decisions. Deterministic output also makes advice reproducible, which post-game review needs.
- **Objective.** The Engine optimizes expected placement, matching the success metric. HP is a resource, converted to rounds left to live, not a goal.
- **Shape.** The Engine is a pure function: `advise(game snapshot, game history, data snapshot, mode) → advice list`, with no hidden state. Derived beliefs such as pool depletion, contested units and streak are computed from the history passed in. Live mode calls it on each state change. Post-game review replays the captured game log through the same function, round by round. Recorded games become deterministic test cases and the basis of the evaluation harness.
- **Two layers.**
  - The **Game plan** layer owns the target comp and its Line (for example "fast 8 at 4-2, Ahri carry"). Comp choice, transition and pivot live here; a pivot is a change of Game plan.
  - **Sub-engines**, one per decision: econ, level and roll; shop; Wisp; items; augments; positioning; carousel and opener. Each reads the current Game plan and the state and emits advice. A sub-engine never changes the Game plan. It may raise a pressure signal (carry contested, augment fits another comp) that the Game plan layer weighs. This prevents contradictory advice, such as items for one comp and shop buys for another.
- **Lookahead.** Only the econ, level and roll sub-engine looks ahead. It simulates a few candidate Lines (the Guide's Line, one level earlier or later, roll-down now versus next stage) to the end of the next stage over the XP and gold calendar, hit odds and the damage model. All other sub-engines are greedy, because they gain little from lookahead and no strong evaluation function exists to search with.
- **Board and lobby strength.** No trained model. A board is matched to the closest MetaTFT comp, starting from that comp's average placement and adjusted for completeness: units against level, star levels and finished items. Lobby position ranks the player's score against opponents' scores in Live mode, from captured boards, with HP as the fallback when opponent boards are missing. This is the weakest part of the Engine, and the evaluation harness should target it first.
- **Advice contract.** Each advice item carries a decision type, an action, an urgency (act this phase, soon, or information), a confidence, a reason as a template plus numbers ("62 % to hit"), and a validity (the state change that ends it). The Engine returns the list ranked by urgency, then by impact on expected placement. Surfaces choose only how many items to show; they never re-rank.
- **Missing or stale data.** Each sub-engine declares the fields it requires. If a field is missing from the capture route (for example no Wisp keys), that sub-engine emits nothing and never guesses. Stale or "changed this patch" statistics lower confidence. Surfaces drop items below a confidence threshold, and voice uses a stricter threshold than the overlay.
- **Heuristics as data.** Logic lives in code. Every number and threshold (Lines, roll depth by HP, the Wisp worth table, item slam rules) lives in a per-patch tunables file beside the hand-kept static file, and the owner override file can change them. Patch day is a data edit, not a code change.
- **Language model.** None in v1. Advice text and post-game review prose come from templates: zero latency, no VRAM, no invented numbers. An 8B model costs 3–4 s per call, too much for a planning phase. LLM phrasing is out of scope for v1, so "Benchmark local LLM inference beside a live TFT game" is closed as out of scope.
- **Hardware.** The Engine runs on the CPU only, with a budget of 100 ms per snapshot on the Ryzen 7 7800X3D. The GPU is left to the game and to a vision model if screen capture is chosen.
- **Mode separation.** The Engine core always ships, because post-game review runs it in both modes and Riot's policy encourages post-game analysis. The separable Live-mode component is the **Live advisor**: the in-game loop that feeds live snapshots to the Engine and surfaces advice. In Baseline mode the Engine runs only after a game ends. In-game, Baseline mode uses the Guide layer (static, stage-keyed) and shop highlighting. Its grey-zone hints (the XP-aware leveling hint, the win-chance estimate) are small explicit Baseline features, not filtered Engine output.

Glossary terms Engine, Game plan, Line and Live advisor added to `CONTEXT.md`.

Graduated from the map's "Sub-engines" fog: "Econ, level and roll Line simulation", "Board and lobby strength heuristic", "Item decisions", "Augment decisions", "Positioning decisions", and "Shop, Wisp and carousel decisions". The Game plan layer is owned by "Transition and pivot domain model".
