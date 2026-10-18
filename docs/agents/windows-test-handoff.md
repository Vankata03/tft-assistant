# Windows shell and probe test handoff

This run checks the build-first launcher, shell/core connection, client phase reporting and read-only probe artifacts. It does not qualify a complete Live coach, Windows OCR accuracy, current production data, capture latency or the historical native abort. Tickets 48, 49, 50 and 55 retain those requirements.

## Prerequisites

Use Windows with PowerShell 7 (`pwsh`), Git, Node.js 22.12 or newer with npm, and uv on PATH. The core requires Python 3.14; uv can install it during sync. The probe requires PowerShell 7: Windows PowerShell 5.1 does not support its certificate and JSON options. Run as the normal user with the Riot client open before starting the probe. Record permission failures before considering a different privilege level.

Have enough local disk space for full-resolution screenshots every 1.5 seconds for up to 75 minutes. Keep the game borderless or windowed and record monitor resolution, DPI scale, HUD scale, locale and game patch. Exclusive fullscreen can produce black captures. Automatic screenshots fall back to the primary monitor when the game is not foreground; filenames ending in `_notgame` identify those frames.

## Pull and setup

Open PowerShell 7. On a machine without a checkout, choose a local parent folder and clone the integration branch:

```powershell
$parentFolder = Read-Host 'Local parent folder for the new checkout'
Set-Location -LiteralPath $parentFolder
git clone --branch implement/mvp --single-branch https://github.com/Vankata03/tft-assistant.git tft-assistant
if ($LASTEXITCODE -ne 0) { throw 'clone failed; retain the error before continuing' }
$repo = Join-Path $parentFolder 'tft-assistant'
```

For an existing checkout, set `$repo` to its local path instead. Keep personal paths out of tracked configuration. Run the following setup from either checkout. If `git status --short` reports changes, preserve them before switching branches or pulling.

```powershell
Set-Location -LiteralPath $repo
git status --short
git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'fetch failed' }
git switch implement/mvp
if ($LASTEXITCODE -ne 0) { throw 'branch switch failed' }
git pull --ff-only origin implement/mvp
if ($LASTEXITCODE -ne 0) { throw 'pull failed; resolve branch divergence before testing' }
git rev-parse HEAD
git status --short
pwsh --version
git --version
node --version
npm --version
uv --version
uv sync --project .\core
if ($LASTEXITCODE -ne 0) { throw 'core dependency sync failed' }
npm ci --prefix .\ui
if ($LASTEXITCODE -ne 0) { throw 'UI dependency install failed' }
```

The explicit `npm ci` updates existing dependencies to the checked lockfile. The launcher only installs dependencies when `ui/node_modules` is absent. No separate `TFT_CORE_TOKEN` setup is required: the shell generates the local authentication token.

For a repeatable software check before opening the shell:

```powershell
uv run --project .\core python -m pytest .\core\tests\test_windows_launcher.py -q
if ($LASTEXITCODE -ne 0) { throw 'launcher workflow tests failed' }
npm --prefix .\ui run typecheck
if ($LASTEXITCODE -ne 0) { throw 'UI typecheck failed' }
```

The launcher tests run the real PowerShell script against stand-in package-manager commands. They establish orchestration and failure handling, not actual npm installation, Electron rendering or Windows capture.

## Launch and inspect

Create a local diagnosis folder outside the checkout and retain the tested commit:

```powershell
$diagnosis = Join-Path $env:LOCALAPPDATA ('tft-assistant\diagnosis\' + (Get-Date -Format 'yyyy-MM-dd_HHmmss'))
New-Item -ItemType Directory -Force -Path $diagnosis | Out-Null
git rev-parse HEAD | Set-Content (Join-Path $diagnosis 'commit.txt')
Start-Transcript -Path (Join-Path $diagnosis 'launcher.txt')
& pwsh -NoProfile -File .\start.ps1
$launcherExit = $LASTEXITCODE
Stop-Transcript
'Launcher exit: ' + $launcherExit
```

`start.ps1` syncs the core, installs missing UI dependencies, builds `ui/out`, then starts Electron preview. A failed sync, install or build stops before preview; a failed preview returns its exit code. Keep the terminal open while the tray app runs. The shell starts its own core, so do not start a second core process manually.

Find TFT Assistant in the tray, including hidden tray icons. Click it or choose **Show status**. With no game, the shell should remain connected and report the client phase or client unavailable. An absent capture configuration should leave capture-dependent content unavailable while the shell/core connection remains usable. Open the client, enter a TFT game, and record whether phase changes appear. Phase visibility alone does not establish that the runtime accepted the session as TFT.

Without qualified local assets, expect missing or unavailable advice. Missing configuration is a useful shell smoke test, not a successful capture test. Silent mode must show no game content or voice. Overlay permission remains disabled until checked geometry and anchors are supplied. A selectable mode does not qualify Live advice or review jobs on the tested Windows device. Quit through the tray menu and retain any shutdown, incomplete-media or recoverable-log warning. The core may take several seconds to finish; a forced close is not a successful flush.

## Required inputs for capture

Use [runtime-boundary.md](runtime-boundary.md) for the settings schema and asset formats. Settings default to `$HOME\.config\tft-assistant\settings.toml`. `TFT_ASSISTANT_SETTINGS`, `TFT_ASSISTANT_CONFIG_ROOT` and `TFT_ASSISTANT_DATA_ROOT` can select local alternatives for this process; paths inside settings resolve relative to that file.

A capture run needs a reviewed profile and artwork, the exact visible owner name and checked game-window title, a matching client locale/name catalog, game configuration establishing windowed or borderless mode, calibrated numeric glyphs, verified reader model assets and an accepted model pointer. Windows OCR also needs the locale language pack. Data needs reviewed patch rules and an immutable validated snapshot with the same identities. Runtime capture additionally needs a positively identified TFT session from LCU. A queue number or screenshot alone is insufficient.

No qualified current-patch profile, genuine glyph set, fitted production models or complete production data package is supplied by this handoff. Do not substitute fixture data or invent missing fields. If reviewed assets already exist locally, validate and refresh them outside an active game using the exact paths selected for settings:

```powershell
$patchDir = Read-Host 'Reviewed patch directory'
$snapshotDir = Read-Host 'Runtime data root snapshots directory'
$sources = Read-Host 'Reviewed sources TOML path'
$overrides = Read-Host 'Reviewed overrides TOML path'
uv run --project .\core tft-data validate "$patchDir" --snapshots "$snapshotDir"
if ($LASTEXITCODE -ne 0) { throw 'data validation failed' }
uv run --project .\core tft-data refresh "$patchDir" --snapshots "$snapshotDir" --sources "$sources" --overrides "$overrides"
if ($LASTEXITCODE -ne 0) { throw 'data refresh failed' }
```

Read refresh warnings and source qualification even on exit zero; a validated snapshot does not prove every source is available. Rejected newer sources retain qualified last-good data where available. With no reviewed inputs, skip these commands and record the unavailable state.

## Probe one game

In a second PowerShell 7 terminal, use the same checkout and start before entering the game:

```powershell
$repo = Read-Host 'Existing tft-assistant checkout path'
Set-Location -LiteralPath $repo
& pwsh -NoProfile -File .\probe\probe.ps1 -PollSeconds 5 -ShotSeconds 1.5 -MaxMinutes 75 -GraceSeconds 90
```

Output goes to ignored `probe/out/<timestamp>/`. Stop with Ctrl+C or allow the 90-second grace period after the game process exits. The maximum duration also bounds collection.

The probe records `env-start.json`, `env-ingame.json` when a game is detected, `env-end.json`, `poll.jsonl`, changed response bodies under `liveclient/`, screenshots under `shots/`, and manual captures under `manual/`. LCU discovery may produce `lcu-help-tft.json` or `lcu-help-raw.txt`. Port 2999 being closed or returning errors is a recorded observation, not proof that the launcher failed. A missing discovery file can mean the client was not readable at startup.

Each poll also reads `/lol-gameflow/v1/session` and `/lol-end-of-game/v1/tft-eog-stats`. The ignored `lcu/receipts.jsonl` records request and response UTC times, HTTP status, and the corresponding JSON body filename. Known authentication material and credential fields are redacted. A three-second request deadline and one-MiB body limit bound collection; failed, oversized or non-JSON responses retain a receipt with an unavailable reason and no body file.

These receipts preserve the observed payload shape for later parser and placement checks. A missing endpoint or response error is not a game result. Local HTTP fixtures verify collection and redaction; real Windows session metadata and end-of-game bodies still need capture and inspection before qualifying the runtime parser or placement extraction.

Follow [probe/CHECKLIST.md](../../probe/CHECKLIST.md) for manual captures and round observations. Any checklist unit or mechanic that does not exist in the tested patch should be marked unavailable rather than forced into the evidence. Take manual screenshots of a normal planning view, one scouted board, an augment offer, a reconnect if tested, and the actual end-of-game screen. Note timestamps, game mode, patch, language, display mode and whether each image belongs to the owner or a scouted player.

## Artifacts and diagnosis

After quitting, keep the diagnosis folder, the entire probe run, and `%LOCALAPPDATA%\tft-assistant\logs\core.log`. Session data defaults to `%LOCALAPPDATA%\tft-assistant`; if `TFT_ASSISTANT_DATA_ROOT` was set, retain the corresponding local session/log/media artifacts there. Preserve configuration and model/profile identity hashes for a capture investigation. Record the error text and the last successful step, plus whether the tray, status window and client phase worked.

Check the newest probe folder locally:

```powershell
$probeRun = Get-ChildItem .\probe\out -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-ChildItem -LiteralPath $probeRun.FullName
Get-Content (Join-Path $probeRun.FullName 'poll.jsonl') -Tail 10
Get-ChildItem (Join-Path $probeRun.FullName 'shots') -File | Measure-Object
Get-Content (Join-Path $env:LOCALAPPDATA 'tft-assistant\logs\core.log') -Tail 80
```

No probe folder, no `poll.jsonl`, missing shutdown artifacts, black screenshots, or repeated native errors need investigation; record which files are absent. Screenshots and environment records can contain account names, desktop content and personal paths. Review and redact before sharing. Never share LCU tokens, API keys or authentication headers. Generated artifacts and credentials must stay out of Git.

## Integrated software checkpoint

The integration branch includes independently reviewed fitting workflows, ordinary-tag hover tooltips, combat planning previews with separate display receipts, and validated legacy review-gap bounds. These are software features awaiting the Windows checks below. Tickets 42, 44, 45 and 55 remain open until their full acceptance conditions are met; production inputs, target-device recognition and performance, and historical native teardown causality remain in tickets 48, 49 and 50.

After setup, check the generated interface and run the complete UI suite before launch:

```powershell
npm --prefix .\ui run check:types
if ($LASTEXITCODE -ne 0) { throw 'generated message types are stale' }
npm --prefix .\ui test
if ($LASTEXITCODE -ne 0) { throw 'UI tests failed; retain the output' }
```

The corrective software values a qualified observed Line with counted paid refreshes from the original decision state, exposes production `reader_disagreement` events and available matching keyframes through protected Debug access, and records unsolicited pivot adoption as `taken_without_call` when no matching call preceded the first movement. Later calls cannot retroactively motivate that movement. Observed adoption does not invent a pivot recommendation, display receipt, cost or follow-rate denominator.

Observed-Line valuation requires a complete, fresh, source-accounted financial ledger across the original horizon, including intervals before, between and after roll bursts. Counted refreshes remain additional to natural shops; affordability and death can truncate them. Unknown spending or rewards, unsupported reward timing, sales, grants, Wisp purchases, active effects, XP-only purchases and unsupported same-round leveling after rolling remain unavailable. Source-qualified fixtures do not establish that an ordinary live PvP recording qualifies.

Review-notice qualification requires the complete renderer-to-core path: a visible notice frame, an owned surface, authenticated membership and current report/job/delivery identities, followed by a durable `review_notice_shown` receipt. Publication time alone is not display time. Record the actual display latency from confirmed game end and any late notice after 30 seconds. The receipt belongs in separate `reviews/<game_id>.notice.json` transport metadata; it must not alter game logs, review inputs, reports, tags or job identity, trigger regeneration, become actionable advice or enter a follow-rate denominator. Hidden notices, including transparent ancestors, must produce no visible receipt. A malformed metadata file must yield a bounded error while keeping that client's review requests usable.

Before testing, compare `git rev-parse HEAD` with the final commit SHA supplied in the owner's handoff. Independent review accepted paid-roll and pivot/Debug corrections at `7a80c488568f687ad2f0b34a2cae3e927306db9e` and the final notice visibility and malformed-metadata corrections at `eb5c88d0cdc97619ef9396b18ad1a6c6c2228fe1`. The integrated source matches that accepted candidate. Use the final handoff receipt to verify the pushed commit; this document alone does not prove remote parity.

Default `uv sync --project .\core` installs the `dev` and `live` groups; `train` is explicit. The existing launcher test and typecheck commands remain required. A shell smoke test can proceed without capture assets: record the missing-settings status, connected core, available modes and clean quit. Without reviewed capture inputs, stop at that result. Do not substitute test fixtures for a profile, glyphs, accepted reader pointer or production snapshot. A complete training suite additionally requires the explicit `train` dependency group, verified external reader weights and the supported local tools, including FFmpeg; skips do not qualify those dependencies.

If the external reader cache and FFmpeg are available, run the full training check separately. Use the verified cache path, not an empty directory:

```powershell
$env:TFT_READER_TEST_MODELS = Read-Host 'Verified external reader model cache path'
uv sync --project .\core --group train --frozen
if ($LASTEXITCODE -ne 0) { throw 'training dependencies failed' }
uv run --project .\core --group train --frozen python -m pytest .\core\tests .\core\packages -q
if ($LASTEXITCODE -ne 0) { throw 'full software suite failed; retain the output' }
```

Record passed, failed and skipped counts and process exit status. Windows may skip explicitly POSIX-only fixtures; those skips do not establish Windows equivalents. Missing weights, training dependencies or codec tools must remain explicit.

With reviewed inputs on Windows, check that ordinary tag tooltips appear after dwelling without intercepting game clicks. During combat, the planning chip may show only a scheduled point from a qualified planning observation in the same round. Its separate `preview_shown` receipt is display evidence, not actionable advice or a follow-rate denominator entry. Record unavailable or paused previews, stale geometry, mode suppression and shutdown warnings rather than treating them as successful Live qualification. These checks still need actual game and device evidence.

This handoff does not start an owner run. `tft-harness start-run` is a separate owner-data workflow that needs a deliberate owner action and qualified baseline inputs. Offline `eval`, `fit` and `fit --priors` require their documented committed tunables, immutable snapshots and qualified evidence; generated candidates remain unaccepted until owner review and commit.

## Verification recorded with this change

PowerShell 7.5.3 on macOS exercised the launcher with external uv/npm stand-ins: fresh checkout order, existing dependency rebuild, and exit-code propagation at sync, install, build and start. Those six cases failed against the old launcher and passed after the change. This is executable orchestration evidence. Windows npm/uv/Electron execution, native capture, real LCU session payloads, source availability and game-device performance still require the run described above.

The receipt helper also ran against a real local HTTP fixture through PowerShell 7.5.3 on macOS. Three cases passed: JSON payloads with successful and missing-endpoint statuses, an oversized response, and a non-JSON response. The checks verified endpoint paths, authentication removal, UTC receipt times, retained session fields and explicit unavailable outcomes. Both probe scripts passed PowerShell parsing. The clone commands remain operator instructions; this check did not clone or run the application on Windows.
