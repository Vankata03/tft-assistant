---
id: 57
title: Build-first Windows launcher and operator test handoff
labels: [implementation:task]
status: open
assignee: codex-windows-handoff
parent: 34
blocked_by: [53]
---

# Build-first Windows launcher and operator test handoff

The owner plans Windows tests tonight and explicitly authorized committing and pushing the changes. Extract this independent launcher and handoff slice from 55; full Engine/Live/jobs and optional login/shortcut integration remain in 55.

## Sources

- [Runtime specification](../docs/spec/runtime.md), [capture runtime boundary](../docs/agents/runtime-boundary.md) and [ticket 55](055-runtime-software-integration.md).
- Existing `start.ps1`, UI build/start scripts, `probe/probe.ps1` and `probe/CHECKLIST.md`.
- Owner-approved CLI/workflow test seam in [implementation contract](../docs/agents/implementation.md).

## Acceptance

- Make the repository launcher build the UI output before invoking its preview/start command, using the existing dependency workflow and preserving failures from sync, install, build and start.
- Provide a bounded Windows operator document with exact pull/setup/launch/probe/check commands, required local inputs, expected available/unavailable states and the artifacts needed for diagnosis. Reuse existing tools and keep personal paths, credentials and generated artifacts out of tracked configuration.
- Distinguish tonight's shell/client/native probes from a complete Live coach. No qualified production patch, profile, glyph set or fitted model is invented. Current source, capture/device, target latency and historical native qualification remain explicit.
- Verify actual public launcher behavior where the environment supports it. Record unavailable Windows/PowerShell execution honestly; do not add string-matching tests that mirror the script.
- Use an isolated worktree, preserve latest integration before exact committed handoff and obtain a different merger. Root owns final commit/push verification.
