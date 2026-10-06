---
id: 46
title: Immutable data contracts and capture name lists
labels: [implementation:task]
status: open
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
