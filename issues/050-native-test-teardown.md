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

This blocks the parent specification and final runtime gate. Ticket 40's independently verified Engine software boundary is closed. Investigation continuity: Vault `10 Projects/TFT Assistant/Issues/Native Python shutdown abort after passing tests.md`.

## Resolution

Unresolved. The failure is reproduced; its initiating cause and a verified fix remain unknown.

## Comments

### 2026-10-11 — Contemporaneous controls and uncertainty

The unchanged original command later passed all 191 tests and exited 0 in 21.02 s, without a dependency, flag or lifecycle change. The 190-test control omitting only the data Riot CLI also exited 0; this does not attribute the earlier failure to that test. Import/construction controls, delayed exit and repeated OCR lifetime probes have not produced a smaller red process. Evidence is in `worktrees/native-teardown-2026-10-11/`.

The ownership follow-up on separate commit `bdad1d9` passed 196 tests and exited 0 with the same two ONNX-export warnings. These favorable runs establish current outcomes only. They neither identify the initiating cause nor resolve the historical abort. Current environment guards were recorded separately; their absence now does not establish their state in the original failed processes. Ticket 50 remains open.

### 2026-10-11 — Verified application startup prevention

The owner authorized a bounded prevention mitigation while retaining the unknown initiating cause. Importing `tft_capture` now sets `ORT_DISABLE_TELEMETRY=1` before the package's optional runtime imports. Core startup, the installed training CLI and direct reader imports share that boundary. The existing post-import API calls remain for the separate legacy Windows telemetry backend. No dependency pin, test omission, forced exit or shutdown-error suppression was introduced.

- Primary contract: [official privacy documentation](https://github.com/microsoft/onnxruntime/blob/main/docs/Privacy.md#disabling-telemetry). Pinned [ORT 1.30.0 initialization](https://github.com/microsoft/onnxruntime/blob/v1.30.0/onnxruntime/core/platform/posix/telemetry.cc#L405-L456) returns before SDK creation for the startup flag. The [runtime API](https://github.com/microsoft/onnxruntime/blob/v1.30.0/onnxruntime/core/platform/posix/telemetry.cc#L704-L729) leaves the uploader live. This supplies a supported prevention mechanism, not a diagnosis of the mutex failure.
- Public regression first failed with `startup_opt_out=None` at the first ORT import, despite successful real OCR and normal child exit. The same process passed after the bootstrap change. Three portable process checks cover real CPU OCR, installed core CLI rejection without its launch token, and training CLI help without eagerly importing ORT or Torch. Import audit hooks observe external library loading; internal collaborators are not mocked.
- `15-application-bootstrap-native-samples.json` compares the same real reader workflow with the startup flag removed from both child environments. The integration control observed the Microsoft telemetry worker and no startup opt-out; the candidate observed opt-out `1` and no Microsoft telemetry frames. Both used ORT 1.30.0, read the same blank fixture and exited normally; both native sampling commands exited 0. This sampled prevention evidence is separate from the unresolved historical abort. Artifact 14 records the preceding supported-flag-only comparison.
- After integrating `b9a4339`, frozen train-group synchronization and the original full-suite command with cached pinned models passed all 212 tests in 18.89 s, process exit 0. Existing CPU recognition, real Torch fine-tuning, export parity and promotion checks remained enabled. The two existing ONNX-export warnings remain. Both import contracts, schema, lock, scoped F821 and diff checks passed. Retained command output and exit codes are in artifact 16. A pre-resume tool session lost its result and is not counted as verification.
- The scoped capture-boundary prose audit preserved all 130 extracted constraints without warnings; phrase and structure scans reported no findings. Preexisting soft document-shape and technical-readability findings were reviewed and retained. No unrelated prose was rewritten.

A host that imports or initializes ORT before capture must apply the startup flag itself; this bootstrap cannot dismantle an existing uploader. `docs/agents/capture-boundary.md` records that boundary. Windows execution, recognition accuracy and device latency remain separate qualification work. Ticket 50 stays open: there is still no minimized red-capable abort reproduction, initiating cause or causal repair. Favorable full-suite exits validate their recorded executions only.

### 2026-10-11 — Independent integration verification

The separate merger reviewed the four-file startup-prevention change and passed its three public process tests before merging exact commit `5d8157e` as `29b3d26`. The integration root then passed all 212 Python tests in 21.98 s, with the two existing ONNX-export warnings and process exit 0. Both import contracts, schema generation and the frozen lock check passed. No UI files changed; the prior 31-test UI/type/generated-type/build verification remains dated evidence. The unknown initiating cause and missing minimal abort reproduction remain open.

### 2026-10-11 — Bounded historical process reproduction search

A separate detached diagnostic worktree at exact `33b83b1` was synchronized with its frozen lock and the training group. Six sequential fresh processes ran the original complete 191-test command with the same cached pinned reader assets. Startup opt-out, unit-test and known CI suppression flags were explicitly removed from these child environments; this establishes the probe conditions, not their values in the historical failed processes. No source, dependency, lifecycle or test omission was introduced.

All six passed 191 tests with the two existing ONNX-export warnings and exited 0. Their pytest durations were 36.24, 9.73, 10.12, 10.16, 10.06 and 10.48 seconds. The exact symptom was not observed. Full command outputs and conditions are retained in ignored `worktrees/native-teardown-2026-10-11/18-historical-full-reproduction.json` and its six stdout/stderr pairs. The diagnostic worktree is `worktrees/native-control-33b`; it contains no implementation edits. This bounded search does not provide a minimized red reproduction or causal repair, so the ticket remains unresolved.
