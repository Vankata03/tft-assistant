---
id: 25
title: "Stack and runtime"
labels: [wayfinder:grilling]
status: closed
assignee: claude-code
parent: 1
blocked_by: []
---

## Question

What language, runtime and packaging does the coach use, and how do capture, the Engine, the game log and the surfaces talk to each other? Constraints already settled: capture is screen capture of the "TFT" window plus the League client API ("Game-state capture route"); OCR and an onnxruntime vision model run on the CPU on changed regions at about 4 Hz; the Engine is a deterministic pure function on the CPU with a 100 ms budget per snapshot ("Advice engine architecture"); the surfaces are an overlay, a second-screen window and voice; the Live advisor must be a separable component that a public build can omit ("Policy stance and feature modes"); data is refreshed between games ("Data source strategy"). Decide the process layout (one process or several), the message format between components, how the overlay draws over a borderless game window, and how the pieces are packaged and started for the owner's Windows 11 PC.

## Comments

### 2026-10-04 — claude-code

Input from "Post-game review scope": post-game review runs as an offline replay job when the League client reports the end of the game, replaying about 300 decision points through the Engine (about 30 s). Its output, one replay record per decision point, is cached with the engine version and the data snapshot id and regenerated on demand. The evaluation harness re-runs the same job over every game log when the engine or the tunables change. The game log must also record every piece of advice shown, with its timestamp and surface.

### 2026-10-04 — claude-code

Input from "Benchmark open-source board recognition on probe frames": v1 reuses TFT-COACH's board reader (MIT), which is Python with onnxruntime and OpenCV; its own app wraps a Python backend in an Electron and React overlay. The reader ran unchanged on Python 3.14.6 with onnxruntime 1.30.0 on the CPU at 24 ms per pass. The Riot API rejects Python's default `urllib` User-Agent through Cloudflare (HTTP 403, `error code: 1010`), so the API client must send its own User-Agent.

### 2026-10-04 — claude-code (resolution)

Resolved by grilling with the owner, who accepted every recommendation. Inputs: "Game-state capture route", "Advice engine architecture", "Policy stance and feature modes", "Data source strategy", "Post-game review scope" and "Benchmark open-source board recognition on probe frames". One fact checked during the session: the probe captured frames with desktop `CopyFromScreen`, which would also capture an overlay drawn over the game.

**Languages**

1. **Python 3.14** (standard CPython build, not free-threaded) runs capture, purchase tracking, the board reader, the Live advisor, the Engine, the game log writer, post-game review and the evaluation harness. The Line simulator is vectorized with numpy. The 100 ms Engine budget is measured during the build. If it is missed, only the simulator's inner loop moves to a compiled extension; the Engine's pure-function contract keeps that change local.
2. **Electron, TypeScript and React** run the overlay and the second-screen window as two windows of one app.

**Processes and messages**

3. **Two long-running processes.** The Electron shell starts the Python **core** as a child process. The core owns capture, purchase tracking, the board reader, the Live advisor, the Engine and the game log writer. The UI owns all three surfaces, including voice.
4. **Threads in the core.** Capture and the Engine run on separate threads. onnxruntime, OpenCV and numpy release the GIL, so an Engine call never stalls a 4 Hz capture tick. Free-threaded 3.14t is not used, because onnxruntime support for it is unverified.
5. **Channel.** A localhost WebSocket carries JSON messages, each with a schema version. The core pushes snapshots and the ranked advice list. The UI sends player actions (pinning a Line, the Live mode switch) and reports each piece of advice it showed, with surface and timestamp; the core writes that report to the game log. Message schemas are defined once as Python models, and JSON Schema generated from them feeds the TypeScript types, so the two sides cannot drift.
6. **Crash supervision.** The Electron shell restarts a dead core with backoff, up to 3 times in 5 minutes. The core re-attaches through the League client API's game id and appends to the same game log. The missed span is recorded as a capture gap, the same as a game crash. The second screen shows a "coach restarting" state, and the overlay hides advice older than the restart.

**Capture and OCR**

7. **Capture method.** Windows.Graphics.Capture (WGC) of the "TFT" window is primary, with the yellow capture border turned off. It reads the window's own content, not windows drawn above it. The overlay windows are also flagged `WDA_EXCLUDEFROMCAPTURE` (Electron `setContentProtection(true)`) as a second guard. Desktop BitBlt is the fallback if WGC fails. A side effect is that OBS, Discord and Game Bar recordings do not show the overlay.
8. **OCR.** Digits (gold, HP, level, XP, timer, stage) are read by template matching against the game font. Names (units, augments, items, Wisps, traits, players) are read with RapidOCR (PaddleOCR models on onnxruntime, CPU) and fuzzy-matched to the client locale's name list from Data Dragon and CommunityDragon. Windows.Media.Ocr is a fallback behind the same interface. A build session benchmarks both on the probe frames before the engine is locked.

**Surfaces**

9. **Voice.** Electron's `speechSynthesis` speaks with the Windows OneCore voices, behind a small text-to-speech interface so that a local neural voice (Piper) can replace it later.
10. **Display mode.** Overlays cannot draw over exclusive fullscreen, so the game must run borderless or windowed. When the core detects exclusive fullscreen, the second screen shows a warning and the overlay stays off.
11. **Overlay input.** The overlay is click-through by default. `setIgnoreMouseEvents(true, {forward: true})` lets single widgets, such as a Line picker, take clicks when hovered. A hotkey hides the whole overlay. Which widgets are interactive belongs to "Advice surface UX".

**Live mode separation**

12. `live` is a separate Python package, and the UI has its own Live module. The core loads `live` only if it is installed and the session switch is on. The Engine core, Baseline features (Guides, highlights, grey-zone hints), post-game review and the harness never import `live`; an import-linter contract enforces the direction. A public build ships without the package and without the UI module.

**Background jobs**

13. **Data refresh** runs at core start and whenever the League client API reports the lobby or end-of-game phase, if the data is older than 6 hours. It never runs during a game. Each refresh writes a new immutable data snapshot directory, and a game keeps the data snapshot it started with.
14. **Post-game review** runs as a subprocess at below-normal CPU priority when the client API reports the end of a game. If the next game starts first, the review keeps running at low priority.
15. **Evaluation harness** is a manual CLI (`uv run tft-harness ...`) and is never scheduled.

**Storage**

16. **Game log.** One append-only JSON Lines file per game is the source of truth; it survives a crash mid-write and replays in order. Keyframes sit beside it as lossless WebP. A SQLite index across games (game id, date, patch, placement, pinned flag, replay-record cache) serves the cross-game list and the harness. It can always be rebuilt from the logs.
17. **Hand-edited files.** The static file, the tunables file and the owner override file are TOML, validated against a schema at load. An invalid file blocks the game start with a clear error. Downloaded statistics stay JSON as fetched.
18. **Locations.**
    - Repo (git): code, plus the static and tunables files per patch, so git history records which tunables each harness run used.
    - `$HOME\.config\tft-assistant\`: settings, the owner override file and the Riot key.
    - `%LOCALAPPDATA%\tft-assistant\`: game logs and keyframes (20 GB media cap), data snapshots, the SQLite index, the replay-record cache and app logs.

**Packaging and repo**

19. **Run from the repo in v1.** `uv` manages the Python environment and npm manages Electron. One launcher script and a desktop shortcut start the Electron shell, which starts the core. It runs as a tray app that idles until the client API reports a game. It starts manually, with an optional "start at login" setting. A real installer (electron-builder plus a frozen Python) belongs with public release, which is out of scope.
20. **Engine version** is the git commit plus a dirty flag. Replay records cached under a dirty version are never reused.
21. **One repo.** `core/` is a uv workspace with `engine`, `capture`, `live`, `review` and `harness` packages; `ui/` holds Electron and React; `schemas/` holds the generated message schemas; `data/` holds the static and tunables files per patch.

Glossary terms Snapshot and Data snapshot added to `CONTEXT.md`. Inputs passed to "Advice surface UX" and "Evaluation harness".

### 2026-10-04 — claude-code

Input from "Evaluation harness": the CLI has two commands. `uv run tft-harness eval` replays every game log and writes a Markdown report beside the logs (gates, calibration curves, the advice diff, flip rates and the capture gap share), always compared against the latest committed tunables file. `uv run tft-harness fit` writes a candidate tunables file, which the owner accepts by committing it to `data/`. The game index records each Live-mode game's 10-game block beside its engine version, and the review store holds the owner's moment tags.
