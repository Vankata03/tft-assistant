---
id: 35
title: Durable sessions and crash-safe game logs
labels: [implementation:task]
status: closed
assignee: codex-session-log
parent: 34
blocked_by: []
---

# Durable sessions and crash-safe game logs

## Sources

- [docs/spec.md](../docs/spec.md)
- [docs/spec/runtime.md](../docs/spec/runtime.md)
- [docs/spec/review-and-harness.md](../docs/spec/review-and-harness.md)

## Acceptance

Session lifecycle, downgrade-only mode rules, installed-Live detection, durable mode recovery, JSONL event log, crash-tail recovery, lossless keyframes, media cap and pinning, rebuildable SQLite index, review locks and run metadata.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

### 2026-10-06 — Implementation result

Implemented the durable storage boundary in `core/src/tft_core/storage.py`. `SessionStore` owns game lifecycle, installed-package mode availability, defaults before and after the Live-mode run, downgrade-only in-game changes, restart reattachment, and append-only ordered JSONL records. Recovery removes only an incomplete final record, preserves committed records, and logs the missed span. A torn first event is also recoverable. Writers share a reentrant lock and cache the next sequence number, avoiding a full log read on each capture tick.

Lossless WebP keyframes and recorder-provided MP4 segments live beside the structured log. The media setting defaults to keyframes. Retention deletes the oldest unpinned media at the 20 GB cap, never structured records; the first 50 eligible Live-mode games are pinned, including the active eligible game. The retention result states when pinned media alone exceeds the cap. The SQLite game and replay-cache index can be recreated from logs and `run.json`, including after index corruption. Index connections close before file replacement for Windows compatibility. Reviews stay locked before the run; owner tags survive regeneration. Replay cache keys include engine version, tunables hash and the game's data snapshot, and dirty engine versions are never reused.

The production core opens the storage service. The LCU watcher supplies the numeric game id from the client session endpoint and retries metadata while its phase event socket is quiet. `CoreServer` accepts a `game_metadata(game_id)` provider for the runtime integration ticket to pin the actual patch, immutable data snapshot, model version, engine version, set and previous-patch flag. Reattachment preserves original metadata. The session-state message exposes `available_modes`, with regenerated JSON Schema and TypeScript types, and the existing tray and status selector hide an uninstalled Live mode. They disable in-game upgrades and filter IPC actions against the same policy. A rendered-selector test checks the public-build surface. Metadata failures are sent as actionable core errors and shown in the status window without stopping the LCU watcher. Capture event production, data-provider wiring, review computation remain the responsibilities of their graph tickets.

Verification after merging the current integration tip (`ce4233b`): `uv run pytest -q` from `core/` passed 72 tests; `uv run lint-imports` kept both contracts; `uv run tft-schemas --check` passed. In `ui/`, generated-type checks, TypeScript checks and 26 tests passed. A real package-absence check passed after `uv sync --no-group live` and `uv run --no-group live --exact`: the storage default was Baseline and the Live package was neither installed nor imported. `uv run --no-group live` alone initially retained the already-installed package; the explicit sync corrected the verification environment. The normal development environment was restored afterward.

These results use macOS filesystem, concurrency, WebSocket and external-LCU-response fixtures. Windows process crash reattachment, actual client endpoint behavior, live game-id joining and live-game capture performance remain separate platform checks; none is claimed by these tests. Software acceptance for this storage ticket is complete.

### 2026-10-06 — codex-merger

Integrated branch `implement/ticket-35` at `d29ea7c` into `implement/mvp` with merge commit `0a86dcd`. No merge conflicts occurred. The integration retained data package metadata, automatic Python package-test discovery, and importlib test loading. Integration verification passed: `uv sync`; all 72 Python tests; both import contracts; schema drift; UI typechecking, all 26 UI tests, generated-type drift, and production build. The merge diff passed `git diff --check`. Sync emitted the existing uv-build version warning but completed successfully. The package-absence check remains the implementer's recorded evidence above; this integration reran the normal development configuration. Windows and live-game checks remain outstanding platform evidence.
