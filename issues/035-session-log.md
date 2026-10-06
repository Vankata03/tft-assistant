---
id: 35
title: Durable sessions and crash-safe game logs
labels: [implementation:task]
status: open
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
