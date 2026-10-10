---
id: 38
title: Own-board recognition and crop training
labels: [implementation:task]
status: open
assignee: codex-board-reader
parent: 34
blocked_by: [47]
---

# Own-board recognition and crop training

## Sources

- [docs/spec/capture.md](../docs/spec/capture.md)
- [docs/spec/patch-workflow.md](../docs/spec/patch-workflow.md)

## Acceptance

Integrate pinned MIT TFT-COACH reader, CPU inference, four specified recognition fixes, merge purchase tracking and reader by confidence with disagreements logged, keyframe crop labeling and held-out training acceptance.

Implement and verify the software fixes, calibration workflow and fail-closed training/promotion gate here. Actual owner-labeled recognition/training acceptance, measured per-champion calibration and Windows accuracy/latency remain in [ticket 49](049-capture-device-qualification.md); a software closure does not claim that evidence.

Implement all referenced requirements. Verify through the approved public seams in [implementation contract](../docs/agents/implementation.md). Record platform checks separately; keep unmet acceptance explicit.

## Comments

### 2026-10-06 — codex (asset preflight)

The required upstream commit resolves to `bf22ac92010aef321b9e67d6f125bb2109c41cf4`. Primary repository: <https://github.com/mallangmallang0619/TFT-COACH>. The pinned model assets include both `.onnx` and external `.onnx.data` files, plus JSON metadata; downloading only `.onnx` is insufficient. Unit weights total about 16 MB and star weights about 6 MB. Upstream configuration skips zero-based bench slot 8 via `UNSAFE_BENCH_SLOTS`; ticket 38 must read all nine. Unit/star inference requests `CPUExecutionProvider`. The full historical benchmark dataset is unavailable here; do not claim equivalent recognition or retraining evidence from the nine committed JPEGs.

### 2026-10-10 — codex (reader software and qualification boundary)

Implemented the pinned MIT geometry/preprocessing with the complete upstream notice, real unit/star CPU ONNX inference, all nine bench slots, widened tall-unit search, reviewed per-champion foot-offset CLI, and Cape/component template preparation with alias and ambiguity handling. Missing Maokai calibration leaves its hex unknown. Localized data names map through stable IDs; Lux forms retain the base visual identity until separate positive form/Origin evidence. Unknown stars/items remain partial observations rather than fabricated Engine values.

Capture now records changed `board_read` observations, model versions and lossless own-board keyframes. Reader/tracking reconciliation logs disagreements and keyframes, keeps high-confidence reader identity, uses unique complete tracking below the threshold, and preserves disputed remaining copies as unpositioned partial units. Complete ownership remains independent evidence; purchases alone cannot establish it. Full capture ticket 37 still supplies complete ownership and lifecycle integration.

Implemented crop harvesting with exact-frame pairing and ownership/copy-count labels; ambiguous crops remain unlabelled. Deterministic split groups whole games and duplicate pixels, verifies immutable image hashes and prevents training/held-out leakage. Offline CPU fine-tuning reconstructs the actual current EfficientNet-B0 ONNX weights, checks initial parity, retains all labels, and verifies candidate export parity. Comparison reports per-class counts, descriptive uncertainty and paired-game regression probabilities on the same split. It requires 20 distinct crops and five held-out games for every current class. Promotion reruns the gate, requires ownership/review label provenance and complete assets, and preserves the last-good pointer on rejection. The committed `models.json` remains the original pinned upstream version; no actual retrained model was accepted and no weights were added to Git.

Actual asset checks prepared all six pinned classifier files under ignored local caches with their committed SHA-256 values. The CPU reconstruction experiment measured maximum absolute logit error `1.6689300537109375e-06`. The real Cape/component source fetch prepared 11 templates after deduplicating Cape/Ring artwork. The committed probe's portal-side bench crop passed through the actual CPU classifier; that regression output is not owner-labelled accuracy evidence. Synthetic Maokai/geometry, tracking, templates and held-out fixtures establish software behavior only.

An initial combined run reached 138 passing assertions but exited 134 during native teardown. A paired run excluding fine-tuning reached 137 passing assertions and also exited 134, disproving training as the necessary trigger. The macOS crash report's triggered thread points to ONNX Runtime `DebugEventSource::DispatchEvent`, `HttpResponseDecoder`, `HttpClientManager` and its telemetry worker. One subsequent unmodified run exited cleanly, so the failure was intermittent. Reader and RapidOCR constructors now call the documented [ONNX Runtime telemetry API](https://onnxruntime.ai/docs/api/python/api_summary.html#onnxruntime.disable_telemetry_events) before creating sessions. Two full post-change runs reached 138 passes and exited 0, preserving all inference/export checks. This removes unnecessary telemetry and produced clean software checks; it does not prove absence of every native-library teardown fault on other hosts.

Public APIs and commands are documented in [capture-boundary.md](../docs/agents/capture-boundary.md). Final verification results will be recorded with the implementation commit. The legacy ONNX export path emits two PyTorch deprecation warnings while its CPU parity check passes.

No owner-labelled full-roster held-out dataset, actual owner-crop retraining, measured Maokai foot offset, Windows reader/capture execution, or target-hardware recognition/latency evidence is available. Those acceptance conditions remain open in [ticket 49](049-capture-device-qualification.md). Full visual choices, active Lux Origin/traits, complete inventory/events and runtime capture integration remain in tickets 37 and 45. Ticket 38 stays open until its software commit is reviewed and integrated.

Final checks on integration base `804c60c`: `uv run --group train pytest -q` passed 139 tests and exited 0; the focused reader/CLI suite passed 17 tests and exited 0. `lint-imports` kept both contracts; `tft-schemas --check`, `uv lock --check`, scoped Ruff checks and `git diff --check` passed. Normal reader/CLI startup imported no Torch. The explicit `prepare-models` CLI fetched and verified the complete pinned bundle, and `BoardReader.from_version` opened version `reader-6be07151812d299b` with `CPUExecutionProvider`. A final provenance regression confirms that a board identity supplied by tracking records the combined reader/purchase-tracking source. The optional style check initially reported import/unused-variable findings; those were corrected while retaining upstream explicit pixel casts for comparison. The bounded documentation preservation check passed 124/124 constraints.
