---
id: 58
title: Launcher fails on a fresh install because the Electron binary is never downloaded
labels: [implementation:task, bug]
status: open
assignee:
parent: 34
blocked_by: []
---

# Launcher fails on a fresh install because the Electron binary is never downloaded

## Reproduction and evidence

On Windows 11 with npm 12.2.0 and Node v26.4.0, at `implement/mvp` `f0ece18`, follow [the Windows handoff](../docs/agents/windows-test-handoff.md): `npm ci --prefix .\ui`, then `pwsh -NoProfile -File .\start.ps1`. Sync, install and build succeed, then preview fails:

```text
error during preview electron app:
Error: Electron uninstall
    at getElectronPath (.../electron-vite/dist/chunks/lib-q6ns0vZr.js:155:19)
Write-Error: UI start failed (exit 1)
```

`ui/node_modules/electron/dist` does not exist. Electron 44.5.1 has no `postinstall` script; its `package.json` exposes the download as an `install-electron` bin instead. `npm ci` therefore installs the package without the binary, and neither `start.ps1` nor the handoff runs that step. Running `npx --no-install install-electron` from `ui/` downloaded `dist/electron.exe`, after which the same `start.ps1` launched the tray app and exited 0 on quit.

npm 12 also blocks `esbuild` install scripts (`npm warn install-scripts ... esbuild@0.25.12, esbuild@0.28.2`). The build still succeeded, so this is noted but not established as a defect.

The existing launcher tests use npm/uv stand-ins and cannot detect this.

## Acceptance

- A fresh checkout on Windows reaches a running Electron tray app through the documented setup and `start.ps1` without manual steps.
- The binary download happens through the package's own installer (or an equivalent supported mechanism), and a failed download stops the launcher with a clear error and non-zero exit.
- Existing installs with the binary present are not re-downloaded.
- The Windows handoff reflects the final setup commands.
- Decide explicitly whether the blocked `esbuild` install scripts need approval (`allowScripts`) or are safe to leave blocked, and record why.

## Comments

### 2026-10-20 — Claude

`start.ps1` now runs `npm --prefix ui run electron:install` after the dependency step and before the build, on every start. The new `electron:install` script in `ui/package.json` calls the package's own `install-electron` bin. The installer exits at once when the matching binary is present, so existing installs are not downloaded again. A failure stops the launcher with `Electron binary install failed (exit N)` and that exit code.

The launcher workflow tests (`core/tests/test_windows_launcher.py`) now expect the new stage, including a failure case and the existing-dependencies case. They failed against the old launcher and pass after the change (7 tests). On Windows, `npm run electron:install` exited 0 with the binary present. With `node_modules/electron/dist` moved aside, it restored `dist/electron.exe` (version 44.5.1) in 1.8 s from the local Electron cache, identical to the previous binary.

The Windows handoff now lists `npm --prefix .\ui run electron:install` after `npm ci` and explains why. Decision on esbuild: the blocked npm 12 install scripts stay blocked. The esbuild install script only validates or fetches the platform binary, and the lockfile already installs `@esbuild/win32-x64` for both esbuild versions (0.25.12 and 0.28.2).

Still open: a fresh-checkout run through `start.ps1` to a running tray app on Windows. This change did not launch the tray app, and the binary restore used the cache rather than a network download.
