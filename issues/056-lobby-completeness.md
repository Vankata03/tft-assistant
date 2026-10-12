---
id: 56
title: Require positive fresh lobby completeness for roster-dependent valuation
labels: [implementation:task, bug]
status: open
assignee: codex-review-harness
parent: 34
blocked_by: [37, 40, 41]
---

# Require positive fresh lobby completeness for roster-dependent valuation

## Reproduction

At integration `3a7bce2`, use the declared synthetic `patch()` and `snapshot()` from `core/packages/engine/tests/test_planning.py`. Call public `evaluate(snapshot(lobby_complete=value, pinned_line={'id':'hold','levels':{},'rolls':{}}), GameHistory(), patch(), 'review')` for `value=True`, `False` and `None`.

Every case produces unpaused econ advice and the same six scored placements, `1.3708828427399904`. The capture boundary already supplies a separate lobby-completeness certificate. A partial or uncertified roster must not be treated as the full alive-opponent set for placement, Line valuation or next-opponent probabilities. The numbers are a software-fixture reproduction, not an owner-game estimate.

## Sources

- [Engine specification](../docs/spec/engine.md), [capture specification](../docs/spec/capture.md) and [approved public seams](../docs/agents/implementation.md).
- `tft_engine.lobby.alive_lobby`, strategic preparation/required-field fingerprints, domain dependencies and deterministic simulation seeds.
- Integrated capture (37), decision (41) and frozen replay (52) contracts; current Live display work (44) already identified the need to suppress partial-roster probabilities.

## Acceptance

- Require a fresh, sufficiently confident literal `lobby_complete=true` wherever valuation or probability needs the full alive roster. Missing, false, non-boolean, stale or insufficient-confidence certificates produce explicit unavailable/paused output, not a smaller implied lobby.
- Apply the guard at the shared responsible layer and preserve it through strategic preparation, actual Line/choice simulation, cache/seed and dependency fingerprints. A completeness change must not reuse a qualified full-roster result. Do not patch only the UI.
- Preserve independent local advice and valid observed pairwise fight metrics where their own required fields are qualified. Missing full-roster coverage must not invent other players or unnecessarily erase independently known outcome facts.
- Add public Engine red/green cases for the reproduced positive/false/missing cases and stale/type/conditional-choice behavior. Update declared positive fixtures with explicit certificates; do not weaken capture freshness, ownership, source or mode guards.
- Run appropriate Engine/replay/runtime/Baseline, import/schema/lock and relevant combined gates. Coordinate 42/44/54 consuming fixtures and requirements; merge current integration before exact committed handoff and use a different merger.

## Scope and qualification

This is a narrow software guard. Current production data and actual Windows capture remain 48/49; historical native causality remains 50. Do not access owner credentials, collect matches, start the measurement run or describe fixture outcomes as live evidence.
