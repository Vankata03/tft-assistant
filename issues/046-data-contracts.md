---
id: 46
title: Immutable data contracts and capture name lists
labels: [implementation:task]
status: closed
assignee: codex-data-layer
parent: 34
blocked_by: []
---

# Immutable data contracts and capture name lists

## Sources

- [Data layer](036-data-layer.md)
- [Data spec](../docs/spec/data.md)
- [Implementation contract](../docs/agents/implementation.md)

## Acceptance

Provide immutable public Entity, Guide, Statistic, TaggedValue and DataSnapshot contracts; validate required source-tagged static and tunable inputs; retain the last good immutable snapshot after failed refresh; supply Data Dragon and CommunityDragon names and icons for capture. Verify through the approved data refresh seam. This verified subset was extracted from ticket 36 to open the capture and Engine frontier while the remaining adapters and commands continue.

## Comments

### 2026-10-06 — codex-data-layer

Implementation boundary: `938d64d9bc44dff874e8c912d105cff58fe832c5`. Three refresh-seam tests passed after failing tests demonstrated missing behavior. Integration verification and merge pending.

### 2026-10-06 — codex-merger

Resolved the extracted prerequisite on integration branch `implement/mvp` in merge commit `dfa6be8`. The data package supplies immutable public contracts, source-tagged required static and tunable fields, last-good snapshot retention after invalid refresh, and capture name/icon lists through CommunityDragon and Data Dragon fixture adapters.

Integration verification on macOS with Python 3.14.7: `uv sync` passed; `uv run pytest tests packages/data/tests` passed all 59 tests (56 core and 3 data refresh tests); `uv run lint-imports` kept both contracts; `uv run tft-schemas --check` passed; `git diff --check` passed. The commands ran from `core/` using the root `worktrees/tooling/bin/uv`. Sync emitted a build-system version warning because the package requires uv-build 0.11 while the installed uv is 0.12.23; both packages still built successfully.

These are fixture and source-boundary checks, not Windows capture or live-game evidence. Ticket 36 remains open for the remaining data adapters, refresh workflows, and CLI implementation; the `tft-data` entry point is declared but its command module is not part of this extracted prerequisite.
