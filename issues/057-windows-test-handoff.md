---
id: 57
title: Build-first Windows launcher and operator test handoff
labels: [implementation:task]
status: closed
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

## Comments

### 2026-10-13 — codex-windows-handoff

Implemented the build-first launcher and [Windows operator handoff](../docs/agents/windows-test-handoff.md). Sync, dependency install and build failures stop preview; every native failure retains its exit code, including preview/start. Existing dependencies still rebuild. Updated the probe checklist screenshot interval to match the script.

Six public CLI workflow tests failed against the old launcher and passed against the fix using portable PowerShell 7.5.3 on macOS with external uv/npm stand-ins, including a checkout path containing spaces. These are orchestration checks, not Windows dependency, Electron or native capture results. Windows execution remains pending. Unslop found no confirmed prose defects; preservation retained all 49 extracted draft constraints. LCU session and end-of-game bodies are not collected by the existing probe. Production assets, runtime integration and native qualification remain in their owning tickets.

### 2026-10-13 — independent integration review

Corrected exact `aaf9ccca17655ee18f876aaa025eb61dbc8473f2` was independently reviewed and merged as `5d5fbd8bb698a99fc21eb22b8af1e3fca7cb0891`. Review corrected a Windows path-separator mismatch in the public workflow assertions without weakening argument count, flags or order checks. Six executable PowerShell workflow cases passed on macOS in 5.23 seconds, process exit 0. All 35 UI tests, typecheck, generated-type checks, build, capture-inspection CLI help and whitespace checks passed. Actual Windows package-manager, Electron, LCU and capture execution remain pending. Full runtime ticket 55 and production qualification 48 remain open.

### 2026-10-14 — Independent guarded LCU receipt integration

The operator-only checkpoint now collects the actual LCU gameflow-session and TFT end-of-game endpoint responses, with UTC/status receipts, a three-second request deadline, a one-MiB response limit and explicit unavailable outcomes. The handoff includes a fresh integration-branch clone path. These artifacts preserve observed response shapes; an error or missing endpoint is not a placement result. No production assets or runtime/desktop draft files were included.

Independent review held original `c7ac333f41f5091b227f26a5dd5e1cc76905f538`: a real local HTTP fixture through PowerShell wrote a nested `clientSecret` credential verbatim. The author corrected recursive secret-key redaction in exact `1e275531200a755413c6f457831a98ddf91b9e31`, preserving case-distinct nonsensitive fields. The permanent public regression checks nested secret naming/case variants, files, stdout and stderr. Review accepted the corrected source from a detached worktree without using the dirty ticket-55 draft.

Corrected detached receipt/launcher verification passed 9 tests in 7.85 seconds, process exit 0. Both PowerShell scripts parsed without errors. An additional real HTTP/PowerShell fixture stalled the session response body and returned a redirect from the other endpoint: the complete two-request run finished in 3.30 seconds, the stalled body was unavailable, HTTP 302 remained recorded, and exactly the two intended requests occurred with no redirect follow, process exit 0. The one-MiB/non-JSON cases retained unavailable receipts without saving those bodies.

After root release at `d47964f`, only the two operator commits were cherry-picked as `198f1bc` and `098a31bcd4f9300b010548cea65fd63b5f15dedb`. Merged-root receipt/launcher checks passed 9 tests in 7.47 seconds, process exit 0; both scripts parsed with zero errors, all four operator files matched the exact corrected author source, and whitespace checks exited 0. Earlier full-suite evidence at `d47964f` predates these operator changes and is not a full-suite check of them. Actual Windows execution, LCU payload/parser and placement qualification, production/live-game behavior, native causality and full ticket 55 remain open. `.DS_Store`, stashes and the dirty runtime/desktop draft were preserved. Nothing was pushed or written to the Vault.
