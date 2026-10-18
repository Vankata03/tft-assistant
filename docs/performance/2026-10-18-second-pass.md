# Performance second pass — 18 October 2026

This pass compares the pushed first-pass checkpoint `e40d9e7` with candidate `8567228` on branch `optimize/performance-2`. It speeds up CPU evaluation without changing rollout counts, candidate enumeration, random seeds, decision values or evidence. Every optimization either reproduces the reference computation exactly or reuses an earlier exact result.

The Engine is faster on every measured fixture, and replay production is about twice as fast. Large fresh Engine evaluations still miss 100 ms on this machine. Capture, OCR, Windows game-running behavior, IPC and renderer presentation were not measured in this pass.

## Measurements

The companion `2026-10-18-second-pass-results.json` records every unprofiled sample, the fixture arguments and the parity results. The timings come from this macOS ARM64 workstation with Python 3.14.7, measured serially on clean checkouts with identical dependencies. They are synthetic software measurements. They do not establish recognition accuracy, fitted-model quality, gameplay results or Ryzen 7 7800X3D qualification.

| Workload | `e40d9e7` | `8567228` | Speedup |
| --- | ---: | ---: | ---: |
| Fresh planning: 65 Guides, 64 rollouts | 272.7 ms | 199.7 ms | 1.37× |
| Fresh combat fixture: 65 Guides, 64 rollouts | 282.8 ms | 211.2 ms | 1.34× |
| Fresh two-slot roster: 65 Guides, 64 rollouts | 567.1 ms | 372.1 ms | 1.52× |
| Fresh augment choice: 12-option pool, 8 Guides, 8 rollouts | 1,641.3 ms | 1,207.2 ms | 1.36× |
| Live, first evaluation: 65 Guides, 64 rollouts | 306.5 ms | 228.2 ms | 1.34× |
| Live, repeated input: 65 Guides, 64 rollouts | 59.2 ms | 41.8 ms | 1.42× |
| Live, repeated input: 12 historical snapshots | 17.3 ms | 11.3 ms | 1.53× |
| Live, repeated input: 120 historical snapshots | 82.7 ms | 55.7 ms | 1.48× |
| First replay production: 300 decisions | 7.16 s | 3.29 s | 2.18× |

Engine rows are medians of seven evaluations. The Live repeated-input rows are medians of the warm evaluations; the first-evaluation row is a single sample. The replay row is one fresh process per checkout, so treat it as directional. Its peak RSS was 144.5 → 145.8 MiB and retained RSS 129.6 → 129.8 MiB, which is within run-to-run variation.

Measured against the first pass's original baseline `aca9768`, fresh planning has gone from 316.5 to 199.7 ms and the two-slot roster from 912.5 to 372.1 ms. Repeated Live input on the 65-Guide fixture has gone from 344.7 to 41.8 ms, and 300-decision replay from 7.83 to 3.29 s. Those figures come from two sessions on the same machine and are less precise than the paired rows above.

## What changed

- **Shop draws.** A shop draw first picks a cost and then a unit of that cost, weighted by the units remaining in the pool. When every pool weight is an integer, the simulator now scans only the roster for the drawn cost. Integer sums are exact in any order, so it selects the same unit as the full-width scan. Fractional contested pools keep the original scan, and so do small batches below 256 rollouts, where one wide array operation costs less than per-cost dispatch. Cost draws, level validation and the interest reserve are computed once per refresh rather than once per slot.
- **Rollout preparation.** Within one evaluation, simulations with identical construction inputs share one prepared rollout board and its board-power memo. Those inputs are the Guide, level, board, bench, trait counts and capacity evidence. The memo key already contained every remaining input to the power calculation. Seeded random tapes are reused for equal seeds and tape addresses. A fight's power is reused as the round's terminal power when passive XP leaves every level unchanged.
- **Board-state grouping.** Identical owned-copy states are grouped with an integer row hash, and every row is then compared exactly with its group's representative. If any comparison fails, grouping falls back to exact byte comparison.
- **History evidence.** Replay previously re-encoded every earlier snapshot for each decision, so its cost grew quadratically with game length. Each immutable snapshot and sighting now keeps its exact JSON and frozen encoding while the object is alive, and history evidence is assembled from those pieces. The bytes and digests are unchanged. The memo holds only weak references, so the cached encodings are released together with their snapshots.
- **Encoding helpers.** `_encode`, `freeze` and the review layer's `json_value` check exact built-in types before the general `typing.Mapping` and dataclass checks. They take the same branch the general checks would take, so subclasses still follow the original path. Dataclass field names are retained per type.
- **Patch calculations.** Trait variants, default growth-curve lookups and standard levels are prepared once per evaluation scope. Callers still receive fresh trait dictionaries. The scope's key handling was also made cheaper.

These changes were tried and then reverted because they made no measurable difference: an evaluation-scope memo for `estimate_strength`, a dictionary index for `round_index`, read-only shared trait variants and lazily stripped unit positions.

## Accuracy and verification

- Complete serialized Engine advice and Line results are byte-identical to `e40d9e7` for the planning, combat, two-slot and augment fixtures.
- The decision-evidence SHA-256 digests match for the 12-snapshot and 120-snapshot Live histories and for the 65-Guide Live fixture.
- The 300-decision replay serializes to the same 8,246,986 bytes. A full-document comparison over 60 decisions differs only in the `commit` and `runtime_source_hash` identity fields.
- New public tests in `packages/engine/tests/test_simulation_exactness.py` cover five cases. Grouped shop picks must match the full-width scan, and scoped reuse must match independent simulations. A forced hash collision must fall back to exact grouping. Encoding fast paths must keep subclass and dataclass semantics, and cached history encodings must match whole-history encoding and be released with their snapshots.
- The full Python suite at `22378a2` passed **1,094 tests with 28 skips** in 916 seconds, exit 0. Fourteen skips need the unavailable PowerShell 7. The other fourteen are in `tests/test_board_reader.py` and `tests/test_capture_complete.py` and need the explicit `train` group, which that environment did not include. After syncing the `train` group, those two files passed **75 tests with zero skips**, with the two existing Torch ONNX-export warnings.
- `8567228` only removes an unused import. After that change, Engine, Live-delivery and replay tests passed **286**.
- Both import contracts, the offline lock check, whitespace checks and scoped Ruff `F821` checks pass. Scoped `F401`/`F841` findings in the changed files match the baseline's.

No production data, owner matches or credentials were accessed. UI code, message schemas and generated types were not changed, so UI tests were not rerun.

## Remaining limits

- The two-slot fixture still needs about 372 ms per fresh evaluation, and the augment fixture about 1.2 s. On fresh evaluations, the remaining cost is mostly per-slot NumPy dispatch in the shop loop and Python-level board selection in `strongest_owned_board` and comp screening. The runtime specification allows moving the inner loop to a compiled extension. That would need packaging work and numerical parity checks on Windows and macOS, and was not attempted here.
- Warm Live evaluations are now dominated by comp screening across 65 Guides, which Live recomputes on every call by design.
- Cached history encodings stay in memory for as long as their snapshots do. Long-game Live memory was not measured.
- Capture-to-screen latency, OCR and recognition speed, and target-hardware timing remain open.

## Reproduce

Create a clean baseline worktree at `e40d9e7` and a candidate worktree at `8567228`. Sync both with `uv sync --offline --frozen`, then run the following from each checkout's `core/`, one benchmark at a time:

```sh
uv run python packages/engine/tests/benchmark_engine.py --guides 65 --rollouts 64 --repeats 7 --result-json planning.json
uv run python packages/engine/tests/benchmark_engine.py --guides 65 --rollouts 64 --combat --repeats 7 --result-json combat.json
uv run python packages/engine/tests/benchmark_engine.py --guides 65 --rollouts 64 --large-unit --repeats 7 --result-json large.json
uv run python packages/engine/tests/benchmark_engine.py --augment-pool 12 --guides 8 --rollouts 8 --repeats 7 --result-json augment.json
uv run python packages/engine/tests/benchmark_engine.py --guides 65 --rollouts 64 --repeats 7 --live
uv run python -m tests.benchmark_live_latency --history 12 --repeats 7
uv run python -m tests.benchmark_live_latency --history 120 --repeats 7
uv run python -m tests.benchmark_replay_resources --decisions 300
```

Compare the `--result-json` files byte for byte and the reported evidence digests between checkouts, as well as the timings.
