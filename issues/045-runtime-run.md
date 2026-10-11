---
id: 45
title: End-to-end runtime, refresh/review jobs and run workflows
labels: [implementation:task]
status: open
assignee:
parent: 34
blocked_by: [38, 42, 44, 50]
---

# End-to-end runtime, refresh/review jobs and run workflows

## Sources

- [docs/spec/runtime.md](../docs/spec/runtime.md)
- [docs/spec/review-and-harness.md](../docs/spec/review-and-harness.md)
- [docs/spec/patch-workflow.md](../docs/spec/patch-workflow.md)

## Acceptance

Wire capture/Engine threads and persistent sessions to supervised core, data refresh at safe lifecycle points, below-normal post-game jobs, baseline refresh and explicit start-run CLI freeze/unlock/numbering/blocks, shortcut/login settings, integration verification and operator documentation. Do not start the owner's run or claim completion of 50 human-played games.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments
