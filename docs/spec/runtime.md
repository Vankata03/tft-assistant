# Stack, runtime and repository layout

Part of the [MVP spec](../spec.md). Sources: [Stack and runtime](../../issues/025-stack-and-runtime.md), [Advice engine architecture](../../issues/011-advice-engine-architecture.md), [Policy stance and feature modes](../../issues/008-policy-stance-and-modes.md), [Evaluation harness](../../issues/027-evaluation-harness.md), [Patch-day and new-set workflow](../../issues/028-patch-day-and-new-set-workflow.md), [Data refresh trigger and silent sessions](../../issues/033-data-refresh-trigger-and-silent-sessions.md).

Hardware: the owner's PC has an AMD Ryzen 7 7800X3D, 32 GB RAM and an AMD Radeon RX 6800 (16 GB VRAM, no CUDA) on Windows 11. The game runs on the GPU; the coach runs on the CPU.

## Languages

- **Python 3.14** (standard CPython, not free-threaded) runs capture, purchase tracking, the board reader, the Live advisor, the Engine, the game log writer, post-game review and the evaluation harness. The Line simulator is vectorized with numpy. If the 100 ms Engine budget is missed, only the simulator's inner loop moves to a compiled extension; the pure-function contract keeps that change local.
- **Electron, TypeScript and React** run the overlay and the second-screen window as two windows of one app, and voice.

## Processes

- **Two long-running processes.** The Electron shell starts the Python core as a child process. The core owns capture, purchase tracking, the board reader, the Live advisor, the Engine and the game log writer. The UI owns all three surfaces.
- **Threads in the core.** Capture and the Engine run on separate threads. onnxruntime, OpenCV and numpy release the GIL, so an Engine call never stalls a capture tick. Free-threaded 3.14t is not used, because onnxruntime support for it is unverified.
- **Channel.** A localhost WebSocket carries JSON messages, each with a schema version. The core pushes snapshots and the ranked advice list. The UI sends player actions (pinning a Line, setting the session mode) and reports each piece of advice it showed, with surface and timestamp. Message schemas are defined once as Python models; JSON Schema generated from them feeds the TypeScript types, so the two sides cannot drift.
- **Crash supervision.** The shell restarts a dead core with backoff, up to 3 times in 5 minutes. The core re-attaches through the League client API's game id and appends to the same game log; the missed span is a capture gap.

## Live mode separation

`live` is a separate Python package, and the UI has its own Live module. The core loads `live` only if it is installed and the session mode is Live. The session mode (silent, Baseline or Live), its default and its rules are in [spec.md](../spec.md#modes-and-policy). The Engine core, Baseline features (Guides, highlights, grey-zone hints), post-game review and the harness never import `live`; an import-linter contract enforces the direction. A second contract limits Baseline features to the Engine's in-game allowlist module ([engine.md](engine.md#mode-separation)). A public build ships without the package and the UI module.

## Background jobs

- **Data refresh** runs at core start and whenever the League client API reports the `Lobby` phase or the end of a game, never during a game. Each run checks every source against its own minimum age and writes a new immutable data snapshot directory only when something was pulled ([data.md](data.md#data-snapshots-and-refresh)).
- **Post-game review** runs as a subprocess at below-normal CPU priority when a game ends ([review-and-harness.md](review-and-harness.md#post-game-review)).
- **Evaluation harness, data and training commands** are manual CLIs and never scheduled:
  - `uv run tft-harness eval`, `uv run tft-harness fit` and `uv run tft-harness fit --priors`;
  - `uv run tft-harness start-run`, run once to start the Live-mode run;
  - `uv run tft-data new-patch <patch>`;
  - `uv run tft-train`.

## Storage

- **Game logs.** One append-only JSON Lines file per game, keyframes as lossless WebP beside it, and a rebuildable SQLite index across games ([review-and-harness.md](review-and-harness.md#game-log)).
- **Hand-edited files.** The static file, the tunables file and the owner override file are TOML, validated against a schema at load. An invalid file blocks the game start with a clear error. Every static-file field carries a `source` tag ([patch-workflow.md](patch-workflow.md)). Downloaded statistics stay JSON as fetched.
- **Engine version** is the git commit plus a dirty flag. Replay records cached under a dirty version are never reused.

### Locations

| Location | Holds |
| --- | --- |
| Repository (git) | Code; the static and tunables files per patch under `data/<patch>/`; `data/patches.toml`; the accepted board-reader model version pointer |
| `$HOME\.config\tft-assistant\` | Settings, the owner override file, the Riot API key, `baseline-matches.json`, `run.json` (the Live-mode run's start time and frozen pre-coach baseline) |
| `%LOCALAPPDATA%\tft-assistant\` | Game logs and keyframes (20 GB media cap), data snapshots, the SQLite index, the replay-record cache, the review store, board-reader model files under `models\`, app logs |

Keeping the tunables file in git means history records which tunables each harness run used.

## Repository layout

```text
core/      uv workspace: engine, capture, live, review, harness packages
ui/        Electron and React (overlay, second screen, voice, Live module)
schemas/   message schemas generated from the Python models
data/      static and tunables files per patch, patches.toml
issues/    the wayfinder map and tickets
docs/      this spec
probe/     probe script, checklist and committed key frames
```

## Packaging and start

- v1 runs from the repository. `uv` manages the Python environment and npm manages Electron.
- One launcher script and a desktop shortcut start the Electron shell, which starts the core. It runs as a tray app that idles until the League client API reports a game. The tray icon shows the session mode, and the tray menu sets it.
- It starts manually, with an optional "start at login" setting.
- A real installer (electron-builder plus a frozen Python) belongs with public release, which is out of scope.
