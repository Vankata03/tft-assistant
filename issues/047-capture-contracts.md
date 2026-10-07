---
id: 47
title: Capture transport, OCR, tracking and visual-reader contract
labels: [implementation:task]
status: open
assignee: codex-capture
parent: 34
blocked_by: [35, 46]
---

# Capture transport, OCR, tracking and visual-reader contract

This prerequisite is split from [ticket 37](037-capture-pipeline.md). It makes the visual-reader seam available without requiring the reader before its own dependency is complete.

## Acceptance

Implement Windows WGC and BitBlt transport, fractional HUD regions and calibration, OCR and name matching, change-only reads with successful-frame freshness confirmation, capture gaps, conservative purchase tracking, and durable snapshots and keyframes. Publish the frame, region, own-view and reader-result contract needed by ticket 38. Verify behavior through the approved snapshot and game-log seams. Separate Windows and live-game qualification from macOS fixture evidence.

Carousel identities, visual item fields and complete automatic board recognition remain in tickets 37 and 38. This prerequisite does not close the full capture requirement.

## Comments

### 2026-10-07 — codex

The existing `implement/ticket-37` worktree owns this initial boundary. Merge its verified prerequisite commit as ticket 47, then build the reader from that integration tip. Ticket 37 stays open until the visual fields and reader integration are complete.
