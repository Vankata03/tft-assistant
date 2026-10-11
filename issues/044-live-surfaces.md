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

### 2026-10-12 — Transport and desktop geometry integration

The bounded implementation notes are `/tmp/tft-assistant-44-transport-notes.md`. Ticket 41's candidate benchmark retains 17,741,188 bytes of full Advice/Line evidence. Preserve full raw scores and paired distributions for offline review, but implement bounded summary/reference delivery, validated revision/mode membership, paged detail requests, awaited sends and coalesced latest state. WebSocket incoming-message limits do not bound outgoing evidence. Treat the note's proposed message budgets as unmeasured design choices; qualify the implemented byte/memory/latency behavior rather than call those values specification limits.

Ticket 53 currently keeps `overlay_allowed=false` when real desktop geometry is unavailable. `WindowsCaptureSource._window` reads physical client bounds, but `CapturedFrame` does not expose them to runtime consumers. Wire positively observed client origin/size, the correct physical-pixel-to-Electron-DIP conversion and reviewed profile anchors through the capture/publication boundary. Clear or hide overlay content on stale geometry, window loss, incompatible fullscreen, restart or mode downgrade. Do not invent a desktop origin or assume one scale factor for mixed-DPI displays. Mac fixture rendering is separate from actual Windows geometry, overlay exclusion and driver qualification in ticket 49.
