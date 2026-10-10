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
