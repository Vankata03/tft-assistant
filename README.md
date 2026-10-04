# TFT Assistant

A personal Teamfight Tactics coach. The MVP spec is [docs/spec.md](docs/spec.md), and the glossary is [CONTEXT.md](CONTEXT.md).

## Layout

- `core/` is a uv workspace on Python 3.14. The `tft-core` root package is the core process. The members `engine`, `capture`, `live`, `review` and `harness` live in `core/packages/`.
- `ui/` is the Electron, TypeScript and React shell, built with electron-vite.
- `schemas/` holds the JSON Schema for the WebSocket messages, generated from `core/src/tft_core/messages.py`.

## Requirements

- uv and Python 3.14
- Node.js 22 or later, with npm

## Start

```powershell
./start.ps1
```

The launcher syncs the Python environment, installs the shell's packages if needed, then builds and starts the shell. The shell runs as a tray app and starts the core with `uv run tft-core`. The tray menu sets the session mode, and clicking the tray icon opens the status window.

Core logs go to `%LOCALAPPDATA%\tft-assistant\logs\core.log`.

For development with hot reload, run `npm run dev` in `ui/`.

## Message schemas

The Python models in `core/src/tft_core/messages.py` define the messages. After changing them, regenerate both outputs:

```powershell
cd core; uv run tft-schemas
cd ../ui; npm run gen:types
```

The checks below fail when either generated file is stale.

## Checks

```powershell
cd core; uv run pytest; uv run lint-imports; uv run tft-schemas --check
cd ../ui; npm run typecheck; npm test; npm run check:types
```

`lint-imports` enforces two contracts:

- Nothing outside `tft_live` imports it.
- Baseline features (`tft_core.baseline`) reach the Engine only through `tft_engine.allowlist`.

A public build syncs without the Live advisor: `uv sync --no-group live`.
