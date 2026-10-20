---
id: 60
title: Status window does not show the client phase
labels: [implementation:task, bug]
status: open
assignee:
parent: 34
blocked_by: []
---

# Status window does not show the client phase

## Reproduction and evidence

The [Windows handoff](../docs/agents/windows-test-handoff.md) says that after clicking the tray icon or choosing **Show status**, the shell "should remain connected and report the client phase or client unavailable".

On Windows at `implement/mvp` `f0ece18`, without capture settings, the status window showed only the mode selector, `Core running`, the capture-settings error, `Live advisor waiting for fresh capture` and a `Post-game review` button. No phase was visible at any point, although the core log tracked `Lobby`, `Matchmaking`, `ReadyCheck`, `ChampSelect`, `GameStart`, `InProgress`, `WaitingForStats`, `PreEndOfGame` and client loss correctly.

The renderer reads `state.gameflow` only to gate layout (`App.tsx:25`, `Cockpit.tsx:542`). The phase is rendered only in the tray tooltip and menu (`ui/src/main/tray.ts`, `describeGameflow`).

## Acceptance

- The status window shows the current client phase, or that the client is unavailable, using the same `describeGameflow` wording as the tray.
- The display updates on phase changes and survives missing capture settings.
- Silent mode rules are unchanged: phase is status, not game content.
- Covered by a renderer test.
