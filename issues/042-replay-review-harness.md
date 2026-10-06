---
id: 42
title: Replay, post-game review and evaluation harness
labels: [implementation:task]
status: open
assignee:
parent: 34
blocked_by: [35, 41]
---

# Replay, post-game review and evaluation harness

## Sources

- [docs/spec/review-and-harness.md](../docs/spec/review-and-harness.md)

## Acceptance

Replay same Engine with historical snapshots/data, explicit choice/cost/scored-option records, grouping/close-call/capture-gap/positioning rules, dirty-safe cache, tags/review locks, all evaluation metrics/naive baselines/game-bootstrap gates/flip reports, chronological fit holdout and tunable-family restrictions.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments
