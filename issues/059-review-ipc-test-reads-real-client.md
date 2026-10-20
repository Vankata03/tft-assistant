---
id: 59
title: Review IPC test fails whenever the League client is running
labels: [implementation:task, bug]
status: open
assignee:
parent: 34
blocked_by: []
---

# Review IPC test fails whenever the League client is running

## Reproduction and evidence

On Windows at `implement/mvp` `f0ece18`, with the Riot/League client open, `npm --prefix .\ui test` reports 132 passed and 1 failed. The failure reproduces when run alone (`npx vitest run test/reviewMainIpc.test.ts`):

```text
FAIL test/reviewMainIpc.test.ts > regenerates a finished review through actual preload and main IPC into the owned Python child
AssertionError: expected true to be false
 ❯ test/reviewMainIpc.test.ts:80:45
     80|       expect(state.gameflow?.clientRunning).toBe(false)
```

The core spawned by the test discovers the real local client: its log shows `Gameflow: client_running=True phase=None`. The test asserts machine state it does not control, so the result depends on whether the owner has the client open. All other UI tests passed in the same run.

## Acceptance

- The test passes and fails independently of whether a real League client is running, for example by isolating the core child from real LCU discovery or by not asserting on gameflow it does not set up.
- The test still exercises the actual preload, main IPC and owned Python child path it was written to cover.
- Verified on Windows with the client both open and closed.
