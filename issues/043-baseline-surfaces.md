---
id: 43
title: Baseline Guides and permitted hints
labels: [implementation:task]
status: closed
assignee: codex-baseline
parent: 34
blocked_by: [36, 39]
---

# Baseline Guides and permitted hints

## Sources

- [docs/spec.md](../docs/spec.md)
- [docs/spec/surfaces.md](../docs/spec/surfaces.md)

## Acceptance

Guide picker/highlights/static layouts/tiers/recipes/carousel/Wisp table, XP hint with passive XP, par win chance over own board and static growth only, stage voice and import allowlist restrictions.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

- 2026-10-10: Implemented the Baseline controller, typed authenticated request/state/selection/shown-event messages, strict mode guards, Electron cockpit/anchored overlay and local stage-voice boundary. The controller calls only the permitted Engine allowlist and never reads opponent sightings. Guide early positions remain unplaced unless explicitly supplied; source-tagged canonical unit-form identity supports shop membership without guessing aliases. Missing data and stale own fields remain visible. Interface and fixture workflow: [Baseline boundary](../docs/agents/baseline-boundary.md).
- Verification on macOS: 131 Python tests, including 9 Baseline public-seam tests; 31 UI tests; both import contracts, JSON schema checks, generated TypeScript checks, TypeScript typecheck, Ruff and production Electron build pass. A temporary indirect Baseline-to-core-to-Engine import probe failed the tightened contract as intended and was removed. TDD regressions covered guide/static hints, once-only stage speech, checked form membership and tier ordering.
- Actual Zen browser fixture checks: Guide A/B selection, explicit final hexes, unplaced early units, recipes/held components, tiers, Wisp table, XP/par facts, unread par pause, Silent content removal and stale-only status, disabled upward in-game switch, disconnect clearing, reconnect and rejected-source unavailable state. Narrow responsive header/picker checked. Local English voice was unavailable; the renderer showed that status and emitted no voice event. T3 resize reported `No preview automation host is available for resize in environment 4b8f2101-d1a1-4523-bd2d-c373f93963f3`; corrected open retry timed out after 30000 ms. The approved native browser fallback supplied the rendered evidence. Console inspection later timed out; no clean-console claim.
- Compared the rendered cockpit with the generated layout concept: dark ink/teal palette, Guide rail, main Guide/par/XP section, paired hex layouts and reference column preserved. Synthetic concept names/icons/patch were deliberately replaced by explicit fixture names or validated source data. Early units stayed unplaced. The concept is visual guidance only, not current TFT data or a recovered historical prototype.
- Production data qualification remains ticket 48; Windows capture exclusion, native anchoring/click-through/focus/fullscreen and OneCore/live-game evidence remain ticket 49. Ticket 45 owns full running lifecycle publication. No production fixture data, push, PR or Vault write was made. Software acceptance is complete; these source/device checks are separate qualification gates.
