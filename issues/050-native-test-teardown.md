---
id: 50
title: Native macOS teardown abort after the full Python suite
labels: [implementation:task, bug]
status: open
assignee: codex-native-teardown
parent: 34
blocked_by: []
---

# Native macOS teardown abort after the full Python suite

## Reproduction and evidence

On integration commit `33b83b1`, run `worktrees/tooling/bin/uv run --no-sync pytest -q` from `core/` after frozen synchronization with the train group and cached pinned reader assets. The full suite passed all 191 assertions twice, with two existing ONNX-export warnings, then terminated with exit 134:

```text
libc++abi: terminating due to uncaught exception of type std::__1::system_error: recursive_mutex lock failed: Invalid argument
```

Four inspected macOS crash reports from October 10–11 show the triggered ONNX Runtime telemetry HTTP worker: `recursive_mutex::lock`, `DebugEventSource::DispatchEvent`, `HttpResponseDecoder::handleDecode`, `HttpClientManager::onHttpResponse`, `WorkerThread::threadFunc`. This identifies the failing thread, not the initiating cause. Existing telemetry disabling has not eliminated the failure.

Engine-only (56 tests), reader-only (23 tests), core-only (117 tests), core plus data (135 tests), and core plus Engine (173 tests) exited cleanly. Passing these subsets does not establish a cause or repair the full-process failure. Bounded diagnostic artifacts are in ignored `worktrees/native-teardown-2026-10-11/`.

## Acceptance

- Minimize a red-capable process reproduction before changing dependencies or lifecycle code. Record ranked, falsifiable hypotheses and change one variable per probe.
- Add regression coverage through a public workflow/process boundary, implement the narrow supported fix in an isolated branch, and verify the original full-suite command exits successfully.
- Preserve recognition, training and Engine checks. Do not skip tests, force process exit, suppress the native error, or claim success from a favorable retry alone.
- Keep macOS process evidence separate from Windows/live-game qualification in ticket 49.

This blocks ticket 40's integration verification and the final runtime gate. Investigation continuity: Vault `10 Projects/TFT Assistant/Issues/Native Python shutdown abort after passing tests.md`.

## Resolution

Unresolved. The failure is reproduced; its initiating cause and a verified fix remain unknown.
