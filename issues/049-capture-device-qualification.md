---
id: 49
title: Qualify recognition, capture and target hardware budgets
labels: [qualification:capture, qualification:device]
status: open
assignee:
parent: 34
blocked_by: [37, 38, 40, 45]
---

# Qualify recognition, capture and target hardware budgets

This ticket retains the owner-data and device acceptance conditions that cannot be established by the macOS software tests in tickets 37, 38 and 40. Completing those software boundaries does not close this qualification work or the parent MVP specification.

## Sources

- [Capture specification](../docs/spec/capture.md)
- [Patch and training workflow](../docs/spec/patch-workflow.md)
- [Runtime specification](../docs/spec/runtime.md)
- [Board-reader benchmark planning](024-benchmark-board-recognition.md)

## Acceptance

Qualify the reader against held-out, owner-labeled game/keyframe groups with the current roster, including Lux forms, five-cost champions, Maokai, components, Tactician's Cape and all nine bench slots. Review measured per-champion foot offsets and HUD calibration. Exercise the candidate training and promotion gate with actual labeled observations; CPU inference or export parity alone does not establish recognition accuracy or improved model quality.

Run the automatic capture and supervised runtime on Windows against the game window. Verify WGC and BitBlt behavior, overlay exclusion, aspect ratios, UI scale, locales and window modes; own-view identity, full captured fields, event reconciliation, capture gaps, calibration and retained logs/media. Preserve explicit unavailable fields and original timestamps when reads fail.

Measure normal and roll-down capture cadence, offer-to-advice latency and the complete Engine snapshot budget on the specified Ryzen 7800X3D/RX 6800 system while the game runs. Keep macOS timings separate. If the Engine exceeds its 100 ms budget, apply and verify the required optimization or compiled inner loop before claiming target qualification.

Record commands, asset/model/data versions, observations and failures. Do not start the owner's measurement run or fabricate played games. If the device or labeled data is unavailable, retain the exact unmet conditions and their evidence requirements rather than closing this ticket.

## Comments

### 2026-10-10 — codex (qualification split)

Ticket 38's software tests exercise pinned CPU inference, all nine bench slots, tall-healthbar retention and reviewed offset calibration, tracking disagreements, crop labeling, game-group holdout, class regression rejection and export parity. No full owner-labeled dataset, measured Maokai foot offset, Windows recognition accuracy or live latency result is available. Those conditions remain here; the parent task remains unfinished.
