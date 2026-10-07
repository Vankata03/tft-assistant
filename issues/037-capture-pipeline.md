---
id: 37
title: Automatic screen capture and purchase tracking
labels: [implementation:task]
status: open
assignee: codex-capture
parent: 34
blocked_by: [47, 38]
---

# Automatic screen capture and purchase tracking

## Sources

- [docs/spec/capture.md](../docs/spec/capture.md)

## Acceptance

WGC/BitBlt capture, fractional HUD anchors and UI scale, OCR/template matching and name matching, change cadence and roll-down cadence, required captured fields, purchase/sell/pick tracking, fight events, stale values, capture gaps and core log integration.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

### 2026-10-07 — codex (dependency split)

Ticket 47 extracts the transport, OCR, tracking and reader contract. Ticket 38 depends on 47; this ticket then consumes the completed reader. This removes the former dependency cycle while keeping full automatic capture acceptance open.

### 2026-10-06 — codex (capture preflight)

The existing shell/core checks pass on macOS. Primary WGC binding documentation is at <https://github.com/NiiightmareXD/windows-capture/blob/main/windows-capture-python/README-Python.md>. `WindowsCapture(cursor_capture=False, draw_border=False, window_name="TFT")` uses event callbacks with `Frame.frame_buffer`, `on_closed`, and a capture control. Verify Python 3.14 Windows wheel availability and exact binding API during implementation. Do not use a desktop capture as proof that WGC excludes the overlay.

The committed probe JPEGs are available in `probe/screenshots/2026-10-04/`; the full 1,112-frame benchmark dataset and research branches referenced in planning tickets are absent from this checkout and origin. Keep calibration, recognition accuracy and Windows live-game checks explicit. Pinned upstream reader source was fetched read-only to the ignored `worktrees/references/tft-coach/` at commit `bf22ac92010aef321b9e67d6f125bb2109c41cf4` for ticket 38.

### 2026-10-06 — codex (freshness integration constraint)

A successful capture of an unchanged region must confirm its previously read fields as fresh without rerunning OCR. Otherwise the change-only cadence would make every unchanged field stale after two seconds. A failed or unavailable region must preserve the original read timestamp, allowing normal stale-field silence. Keep the originating OCR/reader source and confidence when confirming unchanged pixels. Test this through successive public snapshots, including a failed-frame span.
