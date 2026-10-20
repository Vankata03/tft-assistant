---
id: 59
title: Review IPC test fails whenever the League client is running
labels: [implementation:task, bug]
status: closed
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

## Comments

### 2026-10-20 — Claude

Reproduced on Windows with the League client open (phase `None`, no game): the test failed at the `clientRunning` assertion. Changing only that assertion exposed a second failure that the first one had masked: the review regeneration never completed (`reviewReady` stayed undefined even after 90 seconds). Hiding the client from discovery with a temporary local patch gave the same failure, so this second fault does not depend on the client.

A stack dump of the core showed the review job identity blocked in `git rev-parse HEAD` (`tft_review/identity.py`), with the `git.exe` child still running. Cause: the core's `stdin-watch` thread keeps a blocking read pending on the shell pipe, and every child the core starts inherits that pipe as stdin. On Windows a child that queries an inherited pipe with a pending synchronous read stalls at startup. This affects Git identity checks, review workers and any other core child, not only the test.

Fix:

- `core/src/tft_core/app.py`: `_stdin_closed` moves the shell pipe to a private, non-inheritable descriptor for the watcher and points descriptor 0 at the null device, so later children inherit the null device.
- `core/tests/test_live_shutdown.py`: new public process test. A child started while the shell pipe is watched must finish, and the watcher must still detect pipe closure. It failed before the fix (the child never returned) and passes after it.
- `ui/test/reviewMainIpc.test.ts`: waits for a gameflow update with a boolean `clientRunning` instead of asserting `false`. The rest of the test still drives the actual preload, main IPC, core and owned review child.

Verification on Windows: `reviewMainIpc.test.ts` passed with the client open (8 s) and with discovery hidden as if the client were closed (6 s; the temporary patch was reverted). The full UI suite passed: 29 files, 135 tests, with the client open. `test_live_shutdown.py` passed (3 tests).

Residual: if the owner is inside an active game (`InProgress`, `Reconnect`, `PreEndOfGame`) while the UI tests run, review notices are deliberately suppressed and this test will still fail. That is product behaviour, not machine state the test can control without a production discovery override.

Separately, 5 cases in `core/tests/test_outcomes.py` fail on this Windows machine (`test_actual_review_job_collects_outcome_before_historical_evaluation[never_available]` and the four `test_stalled_external_launch_is_bounded_and_late_child_cannot_collect` variants). They do not use the stdin watcher and were failing before this change; they need their own ticket.
