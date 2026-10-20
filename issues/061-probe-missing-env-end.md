---
id: 61
title: Probe run ended without writing env-end.json
labels: [implementation:task, bug]
status: open
assignee:
parent: 34
blocked_by: []
---

# Probe run ended without writing env-end.json

## Reproduction and evidence

On Windows at `implement/mvp` `f0ece18`, the owner ran `probe/probe.ps1 -PollSeconds 5 -ShotSeconds 1.5 -MaxMinutes 75 -GraceSeconds 90` for one ranked TFT game (run folder `probe/out/2026-10-20_191350`, ignored). The run produced `env-start.json`, `env-ingame.json`, `lcu-help-tft.json`, `poll.jsonl` (5494 lines), 2661 screenshots and LCU bodies with receipts, but no `env-end.json`. The probe process was no longer running afterwards.

Timeline from `poll.jsonl`: the last poll with the game process was 19:50:11; polls without it continue every ~6.7 s until 19:51:46, which matches the 90-second grace break. `Save-Env 'end'` runs in the `finally` block after that break, so it either threw before `Set-Content`, or the terminal was closed at that moment. Closing the window would skip `finally`; Ctrl+C would not. It is not yet known which happened, or whether the console showed the final `Done.` line.

Separately, polls ran every ~6.7 s rather than the requested 5 s after the client went away, because each LCU receipt request waited for its timeout.

## Acceptance

- Determine the cause: reproduce a grace-period exit and a Ctrl+C exit on Windows and check for `env-end.json` and the `Done.` line.
- If `Save-Env` can throw, the probe still writes `env-end.json` with whatever fields are available, and reports the error.
- If closing the window is the only cause, the handoff tells the operator to wait for `Done.` or use Ctrl+C.
- The poll interval behaviour with an unavailable client is either fixed or documented.

## Comments

### 2026-10-20 — Claude

Reproduced on Windows 11 with the League client open, using a stand-in windowed process named `FakeTFT-Shipping.exe`:

- Grace-period exit (`-GraceSeconds 15`, and again with 10): `env-end.json` written and `Done.` printed.
- Maximum-duration exit (`-MaxMinutes 1`, no game): `env-end.json` written and `Done.` printed.
- Ctrl+C: not reproduced. A `GenerateConsoleCtrlEvent` sender did not stop the probe in its separate console, so this needs an operator at a real console.

`Save-Env` has no statement that can stop the `finally` block with the default `Continue` preference, so the most likely cause of the missing file remains a closed window or terminated console. That is not proven.

Changes in `probe/probe.ps1`:

- `finally` writes `env-end.json` first, before the possibly slow manual-capture copy.
- `Save-Env` collects each field separately. A failing field is recorded under `Errors`, reported on the console, and the file is still written. A serialization failure writes a minimal record with the error. A check that made display enumeration throw produced a complete file with `Errors.Displays`, and arrays kept their original JSON shape.
- The header and the handoff tell the operator to wait for `Done.` or use Ctrl+C rather than closing the window.

The handoff now documents that `-PollSeconds` is a minimum spacing. Each poll waits for its LCU and Live Client requests (three-second deadline each), so a slow or unavailable client spaces polls further apart. A slow poll also delays the next screenshot.

Still open: the owner's Ctrl+C and window-close checks.
