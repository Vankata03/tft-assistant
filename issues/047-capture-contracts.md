---
id: 47
title: Capture transport, OCR, tracking and visual-reader contract
labels: [implementation:task]
status: closed
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

### 2026-10-07 — codex-capture (software boundary implemented)

Implemented Windows WGC with border suppression, client-area BitBlt fallback, mixed-DPI thread coordinates, window rescanning and lifecycle recovery. Added anchored fractional HUD regions, game-config UI scale, explicit calibration overrides and a first-round calibration-status hook. Added local CPU RapidOCR, Windows OCR and game-font template adapters, locale-name matching, unchanged-pixel freshness, capture gaps, conservative shop/Wisp purchase transitions, roll-down scheduling, durable snapshots and keyframes. Published the injectable visual-reader contract in [capture-boundary.md](../docs/agents/capture-boundary.md).

The approved capture/log seam verifies against the real SessionStore. Red/green cases cover missing frames, unchanged OCR and visual fields, first-frame own-to-opponent transitions, own-trait rejection, purchase ambiguity, purchases between normal round reads, paid-roll cadence, calibration failure and positively observed empty shops. The committed probe's known gold value 28 is read by the actual bundled CPU RapidOCR models. Full software checks: 107 Python tests; both import contracts; generated schemas; uv lock validation; diff whitespace check. Integration tip 9f80fde was merged before verification.

This closes the prerequisite software contract. Windows API and CPython 3.14 AMD64 wheel availability were checked against primary sources, but no Windows runtime, overlay-exclusion, recognition-accuracy or live-latency result is claimed. Genuine game-font templates and full HUD calibration remain to be prepared and qualified. Runtime45 must call the calibration hook and manage the capture thread. Ticket37 remains open for reader integration, carousel/items, complete player rows, copy/sell/pick/gift reconciliation, fights, video sampling and performance qualification.

### 2026-10-07 — codex-merger

Integrated prerequisite commit `adcd5f2` into `implement/mvp` with merge commit `4414d29`, without conflicts. Source inspection confirmed that own board and inventory fields require a same-frame owner-label confirmation; opponent sightings require same-frame round, trait rows, hidden-row count, opponent label and level. Unchanged successful frames confirm recognition freshness; missing frames, failed reads and a switch to an opponent do not advance the previous own-board timestamp.

Integration checks passed from `core/`: `uv sync --locked`, all 107 Python tests including 16 capture tests, both import contracts, schema drift and `uv lock --check`. In `ui/`, typechecking, all 26 UI tests and generated-type drift passed. The merge diff passed `git diff --check`. Sync emitted the existing uv-build version warning and completed successfully. These are macOS source and public-boundary results, including one actual CPU OCR probe field; Windows transport execution, full recognition accuracy and live-game latency remain unqualified. Ticket 37 remains open.
