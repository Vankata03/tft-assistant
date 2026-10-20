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
