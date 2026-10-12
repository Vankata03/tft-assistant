---
id: 54
title: Model sourced unit slot costs and team capacity
labels: [implementation:task, bug:engine]
status: open
assignee: codex-capacity-engine
parent: 34
blocked_by: [36, 39, 40, 41]
---

# Model sourced unit slot costs and team capacity

Production preparation exposed a concrete representation gap: the current board-power guard and strongest-owned selector compare `len(board.units)` with level. A two-slot unit can therefore be recommended without reserving its second slot, while extra team capacity cannot be represented consistently. This software correction is separate from qualifying the actual patch values in ticket 48.

## Sources and evidence

- [Engine specification](../docs/spec/engine.md), [decision engines](../docs/spec/sub-engines.md), [trait inference](030-opponent-model-from-trait-only-sightings.md), and final [decision contract](../docs/agents/decision-contracts.md).
- Checked October 10 CommunityDragon payload at ignored `worktrees/references/cdragon/latest-en_us-2026-10-10.json`, SHA-256 `17d19792f662cec404aa071492ae9144a2d2677d8db9b52a47a9c7`.
- Its `DA_18_ApexPredator` description explicitly states Elder Dragon takes two slots and grants two Riftbeast. Playable `DA_18_ElderDragon` carries that trait. The cached `DA_Riftbeast18` effect at `minUnits=10` has `TeamSize=2.0`.
- Riot's [July 27 prelaunch overview](https://teamfighttactics.leagueoflegends.com/en-sg/news/game-updates/enchanted-wilds-overview/) says Elder Dragon occupies two slots/contributes two Riftbeast, but lists the maximum-team-size bonus as one and warns values may change. Preserve that dated conflict; neither value becomes a hardcoded current rule.

## Acceptance

- Define one deep, source-aware capacity boundary distinguishing physical unit count, occupied team slots, hex positions and maximum team-slot budget. Represent explicit per-unit slot costs and supported capacity modifiers, including trait breakpoints and positively captured capacity where available. Document how ordinary-unit rules are sourced. No untagged one-slot fallback may silently qualify an unknown unit.
- Validate finite integral costs and modifier shapes, reject booleans and invalid/conflicting metadata, and preserve unavailable status when required capacity evidence is missing. Keep canonical/shared-pool identities and trait-grant multiplicities consistent; Elder Dragon's Riftbeast contribution is two in total, not an extra two on top of one.
- Apply the boundary consistently to own-board power/validation, strongest-owned and forced-Guide selection, transitions, Line simulation, physical unit grants/polymorph/choices, and trait-only opponent inference where team-size constraints enter. Keep distinct observed unit-count and slot-budget evidence separate; do not manufacture opponent units or extra capacity.
- Preserve legality when a larger unit needs room, when capacity appears/disappears with a proposed trait/item state, and when owned units have duplicate identities. Do not score an illegal board as a valid stronger alternative. Any unsupported capacity activation/transition rule must pause the dependent valuation rather than infer an executable sequence.
- Verify through approved public Engine/data boundaries: two-slot selection versus ordinary units, legal and over-budget boards, explicit breakpoint bonuses, malformed/missing metadata, forced-Guide limits, same-seed Line/choice valuation and applicable inference constraints. Use source-tagged fixtures with declared rules; tests are not current patch or device qualification.
- Preserve other planning/ownership/freshness/phase gates and paired evidence. Merge current integration before a clean exact handoff and obtain a different merger agent. Reconcile the final consumer shapes with ticket 48's isolated preparation before any production candidate claim.

## Qualification boundary

This implements consuming sourced rules. Ticket 48 still qualifies real slot costs, capacity bonuses, grants and other patch mechanics. Ticket 49 retains Windows capture and target-device evidence. No owner API, game, run, fit or production data publication is authorized by these software fixtures.
