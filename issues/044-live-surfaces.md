---
id: 44
title: Separable Live advisor, overlay, cockpit and voice
labels: [implementation:task]
status: open
assignee:
parent: 34
blocked_by: [37, 41, 43]
---

# Separable Live advisor, overlay, cockpit and voice

## Sources

- [docs/spec/runtime.md](../docs/spec/runtime.md)
- [docs/spec/surfaces.md](../docs/spec/surfaces.md)

## Acceptance

Live advisor package and UI module separable, versioned messages, ranked advice surfaces/anchors/tooltips/limited overlay input, cockpit/projections/opponents/roll tracker/pins, freshness/paused/fullscreen/restart handling, voice rules, shown-advice/latency events and review UI.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

### 2026-10-11 — Replay attribution prerequisite

Ticket 42 preflight found that current `SurfaceShown`/`ui_show` events contain only surface, content ID and mode. A Baseline content ID is a render revision; it does not identify an advice decision or its options. Persist a versioned delivered-advice record and map each actual surface acknowledgement to its stable decision/option IDs. Followed/ignored status and follow rate must use confirmed display events, never Engine generation alone. Record delivery and display times separately for latency and stale/too-late analysis; keep Silent and mode-boundary enforcement intact.
