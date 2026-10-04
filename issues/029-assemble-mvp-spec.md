---
id: 29
title: "Assemble the MVP spec"
labels: [wayfinder:task]
status: open
assignee: Ivan Terziev
parent: 1
blocked_by: []
---

## Question

Write the MVP spec that the map's Destination calls for: one document, ready to hand to build sessions, compiled from the closed tickets listed in the map's *Decisions so far*. This ticket makes no new decisions. Every statement in the spec traces to a closed ticket, and each section links the tickets it draws on.

Do:

- **Location and shape.** Write the spec as `docs/spec.md`, split into linked files under `docs/spec/` only if one file grows past easy reading. Suggested sections: purpose and success measure; modes and policy; game-state capture; data sources and refresh; the Engine and each sub-engine (econ, level and roll Lines; board and lobby strength; transitions and pivots; items; augments; shop, Wisp and carousel; positioning); advice surfaces; game log, post-game review and evaluation harness; stack, runtime and repository layout; patch-day and new-set workflow; tunables index (every tunable, its owning sub-engine and its family); out of scope; open items.
- **Terms.** Use the glossary in `CONTEXT.md` exactly, and link to it rather than redefining terms.
- **Build order.** Propose an order of build slices that gets silent games logging early, since silent games feed the pre-coach baseline and the evaluation harness. Present it as a proposal for the owner to accept, not a decision.
- **Gaps and contradictions.** Where two tickets disagree, or the spec needs a decision no ticket made, do not decide it. List it under the spec's open items and raise it on the map as a new ticket.
- **Open items.** Carry the map's *Not yet specified* fog (the dedicated TFT client re-check) and the open build facts the tickets name, for example whether MetaTFT's `comp_augment_tiers` holds per-comp augment statistics.
- **Prose pass.** The spec is a human-facing project document, so finish with an `unslop` cleanup pass and its preservation check against the draft.

Resolved when `docs/spec.md` is committed, the owner has read it, and every gap it found is either a new ticket on the map or answered by an existing one.

## Comments

### 2026-10-04 — claude-code

Progress, not a resolution: the draft is committed and waits for the owner to read it.

- **Spec.** [`docs/spec.md`](../docs/spec.md) holds purpose and success measure, modes and policy, an architecture sketch, the build-order proposal, out of scope and open items. It links nine area files under [`docs/spec/`](../docs/spec/): capture, data, engine, sub-engines, surfaces, review and harness, runtime, patch workflow, and the tunables index. One file would have run past easy reading, and build sessions can load only their area.
- **Prose pass.** `unslop` cleanup found no hard or soft phrase hits; its two soft structure flags (repeated openers in the build-order list, a "coda" that is the tunables index's final fact) are genre-natural, so no text changed. The preservation check passed on all ten files against the draft.
- **Gaps raised as tickets**, all grilling, all on the frontier:
  - [Opponent model from trait-only sightings](030-opponent-model-from-trait-only-sightings.md): scouted boards give traits only, but opponent board power, comp labels, the contested count, the pool reduction and the simulator's opponent start assume units.
  - [Baseline mode and opponent sightings](031-baseline-mode-and-opponent-sightings.md): opponent-board data is Live mode only, yet Baseline mode's win chance comes from sightings, and "the Engine runs only after a game ends" in Baseline mode conflicts with that in-game win chance.
  - [Families for unassigned tunables](032-families-for-unassigned-tunables.md): about 20 tunables have an owner but no family.
  - [Data refresh trigger and silent sessions](033-data-refresh-trigger-and-silent-sessions.md): per-source minimum ages against a flat 6-hour check, and no way yet to start a silent session.
- **Answered already.** The ticket's example open fact, whether MetaTFT's `comp_augment_tiers` holds per-comp augment statistics, was answered by "Augment decisions": it holds curated tiers, and no Set 18 augment statistics exist.
- **Open build facts** carried in the spec without tickets, because none needs a decision: the `tft-eog-stats` endpoint, the OCR benchmark, the Engine budget, the board-reader fixes and item bench, reading the current opponent per combat round (the probe's field list did not include it), PvE orb gold and per-unit damage defaults, the pending personal key, and the overlay hotkey.
- **Build order** is a proposal for the owner, starting with capture and the game log so silent games log early.

Remaining to resolve: the owner reads the spec and accepts, reorders or rejects the build order.
