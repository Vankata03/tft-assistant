<#
.SYNOPSIS
  Read-only probe of local TFT data sources during one live game.

.DESCRIPTION
  Records, under probe/out/<timestamp>/:
    env.json             displays, DPI, Riot/Overwolf processes, their listening ports
    lcu-help-tft.json    League client API endpoints whose names mention TFT (once)
    poll.jsonl           one line per poll: port 2999 status per endpoint, client gameflow phase
    liveclient/*.json    each distinct port 2999 response body (saved only when it changes)
    shots/*.png          full-resolution screenshots of the game's monitor every -ShotSeconds (default 1.5)
    manual/              Win+PrtScn and Game Bar captures taken during the run (copied at exit)

  Nothing here reads game memory, sends input or writes to any Riot process. The League
  client API is queried with GET only, using the auth token from the client's own lockfile;
  the token is never written to disk or printed.

  Stop with Ctrl+C, or it stops by itself -GraceSeconds after the game process exits.
  Wait for the final "Done." line before closing the window: closing it skips the
  end record and the manual-capture copy.
#>
param(
  [int]$PollSeconds = 5,
  [double]$ShotSeconds = 1.5,
  [int]$MaxMinutes = 75,
  [int]$GraceSeconds = 90,
  [string]$OutRoot = (Join-Path $PSScriptRoot 'out')
)

$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'lcu-receipts.ps1')
$start = Get-Date
$out = Join-Path $OutRoot ($start.ToString('yyyy-MM-dd_HHmmss'))
$null = New-Item -ItemType Directory -Force -Path $out, "$out/liveclient", "$out/shots", "$out/manual"

Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ProbeNative {
  [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr v);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
'@
# Per-monitor DPI awareness, so screen bounds and captures are in physical pixels.
$null = [ProbeNative]::SetProcessDpiAwarenessContext([IntPtr](-4))

function Log($msg) { Write-Host ("[{0:HH:mm:ss}] {1}" -f (Get-Date), $msg) }

# Processes that look like Riot, TFT or Overwolf. TFT now runs on Unreal Engine, so the game
# executable name is not assumed; anything under a Riot install path or with a matching name counts.
$namePattern = 'League|Riot|TFT|Teamfight|Tactics|Overwolf|vgc|vgtray|Unreal|Shipping'
function Get-GameProcesses {
  Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match $namePattern -or $_.ExecutablePath -match 'Riot Games|Overwolf'
  } | ForEach-Object {
    $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
    [pscustomobject]@{
      Pid         = $_.ProcessId
      Name        = $_.Name
      Path        = $_.ExecutablePath
      WindowTitle = $p.MainWindowTitle
      Version     = if ($_.ExecutablePath) { (Get-Item $_.ExecutablePath -ErrorAction SilentlyContinue).VersionInfo.ProductVersion }
      StartTime   = $p.StartTime
    }
  }
}

# Companion apps (TFT Academy, Blitz, MetaTFT and the like) are recorded but never taken for the game.
$companionPattern = 'Academy|Blitz|Mobalytics|Porofessor|MetaTFT|tactics'

# The in-game process: has a window, is not a launcher, client UI or anti-cheat tray.
function Find-GameProcess {
  Get-GameProcesses | Where-Object {
    $_.WindowTitle -and $_.Name -notmatch 'Riot ?Client|League ?Client|Overwolf|vgtray|vgc' -and
    $_.Name -notmatch $companionPattern -and $_.Path -notmatch 'Overwolf|AppData'
  } | Select-Object -First 1
}

function Get-ListeningPorts($pids) {
  Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $pids -contains $_.OwningProcess } |
    Select-Object LocalAddress, LocalPort, OwningProcess
}

function Get-Displays {
  [System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
    [pscustomobject]@{ Name = $_.DeviceName; Primary = $_.Primary
      X = $_.Bounds.X; Y = $_.Bounds.Y; Width = $_.Bounds.Width; Height = $_.Bounds.Height }
  }
}

# Each field is collected separately: a failure keeps the other fields, is named
# in Errors, and is reported, so the record is always written.
function Save-Env($tag) {
  $record = [ordered]@{ Tag = $tag; Time = (Get-Date).ToString('o') }
  $errors = [ordered]@{}
  $procs = @()
  try { $procs = @(Get-GameProcesses) } catch { $errors.Processes = $_.Exception.Message }
  $fields = [ordered]@{
    Displays  = { ,@(Get-Displays) }
    DpiScale  = { (Get-ItemProperty 'HKCU:\Control Panel\Desktop\WindowMetrics' -ErrorAction SilentlyContinue).AppliedDPI }
    Processes = { ,$procs }
    Listening = { ,@(Get-ListeningPorts $procs.Pid) }
  }
  foreach ($name in $fields.Keys) {
    try { $record[$name] = & $fields[$name] } catch { $errors[$name] = $_.Exception.Message }
  }
  if ($errors.Count) {
    $record.Errors = $errors
    Log "env-$tag.json is incomplete: $(($errors.Keys | ForEach-Object { "${_}: $($errors[$_])" }) -join '; ')"
  }
  try {
    $json = $record | ConvertTo-Json -Depth 5 -ErrorAction Stop
  } catch {
    Log "env-$tag.json fields could not be serialized: $($_.Exception.Message)"
    $json = [ordered]@{ Tag = $tag; Time = $record.Time; Errors = @{ Serialize = $_.Exception.Message } } | ConvertTo-Json
  }
  Set-Content "$out/env-$tag.json" $json
}

# League client API (LCU) credentials, read from the running client's command line.
function Get-Lcu {
  $ux = Get-CimInstance Win32_Process -Filter "Name='LeagueClientUx.exe'" -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $ux -or -not $ux.CommandLine) { return $null }
  $port  = [regex]::Match($ux.CommandLine, '--app-port=(\d+)').Groups[1].Value
  $token = [regex]::Match($ux.CommandLine, '--remoting-auth-token=([\w-]+)').Groups[1].Value
  if (-not $port -or -not $token) { return $null }
  $b64 = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("riot:$token"))
  @{ Base = "https://127.0.0.1:$port"; Headers = @{ Authorization = "Basic $b64" }; Secrets = @($token, $b64, "riot:$token") }
}

function Invoke-Get($url, $headers = @{}) {
  try {
    $r = Invoke-WebRequest -Uri $url -Headers $headers -SkipCertificateCheck -TimeoutSec 3 -ErrorAction Stop
    @{ Status = [int]$r.StatusCode; Body = $r.Content }
  } catch {
    $code = $_.Exception.Response.StatusCode.value__
    @{ Status = if ($code) { $code } else { 0 }; Error = $_.Exception.Message
       Body = if ($code) { $_.ErrorDetails.Message } else { $null } }
  }
}

$liveEndpoints = 'allgamedata', 'activeplayer', 'playerlist', 'eventdata', 'gamestats'
$lastHash = @{}

# A refused localhost connection takes about 2 s on Windows, which would stall the screenshot
# clock; a 300 ms socket check skips the HTTP calls while the port is closed.
function Test-Port2999 {
  $c = [Net.Sockets.TcpClient]::new()
  try { $c.ConnectAsync('127.0.0.1', 2999).Wait(300) -and $c.Connected } catch { $false } finally { $c.Dispose() }
}

function Poll-LiveClient {
  $result = [ordered]@{}
  if (-not (Test-Port2999)) { $result.port2999 = 'closed'; return $result }
  foreach ($ep in $liveEndpoints) {
    $r = Invoke-Get "https://127.0.0.1:2999/liveclientdata/$ep"
    $entry = [ordered]@{ status = $r.Status }
    if ($r.Error) { $entry.error = $r.Error }
    if ($r.Body) {
      $hash = [BitConverter]::ToString([Security.Cryptography.SHA1]::HashData([Text.Encoding]::UTF8.GetBytes($r.Body)))
      $entry.bytes = $r.Body.Length
      if ($lastHash[$ep] -ne $hash) {
        $lastHash[$ep] = $hash
        $file = "{0}_{1:HHmmss}.json" -f $ep, (Get-Date)
        Set-Content "$out/liveclient/$file" $r.Body
        $entry.saved = $file
      }
    }
    $result[$ep] = $entry
  }
  $result
}

function Save-Screenshot($gameProc) {
  # Capture the monitor that holds the game window (foreground window if it is the game,
  # otherwise the primary monitor).
  $screen = [System.Windows.Forms.Screen]::PrimaryScreen
  $fg = [ProbeNative]::GetForegroundWindow()
  $fgPid = 0; $null = [ProbeNative]::GetWindowThreadProcessId($fg, [ref]$fgPid)
  $isGame = $gameProc -and $fgPid -eq $gameProc.Pid
  if ($isGame) {
    $rect = New-Object ProbeNative+RECT
    $null = [ProbeNative]::GetWindowRect($fg, [ref]$rect)
    $screen = [System.Windows.Forms.Screen]::FromPoint([System.Drawing.Point]::new([int](($rect.Left + $rect.Right) / 2), [int](($rect.Top + $rect.Bottom) / 2)))
  }
  $b = $screen.Bounds
  $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  try {
    $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
    $name = "{0:HHmmss_fff}{1}.png" -f (Get-Date), $(if ($isGame) { '' } else { '_notgame' })
    $bmp.Save("$out/shots/$name", [System.Drawing.Imaging.ImageFormat]::Png)
    $name
  } finally { $g.Dispose(); $bmp.Dispose() }
}

# ---- one-time snapshot ----
Log "Output: $out"
Save-Env 'start'
$lcu = Get-Lcu
if ($lcu) {
  $help = Invoke-Get "$($lcu.Base)/help?format=Console" $lcu.Headers
  if ($help.Body) {
    $tft = ($help.Body | ConvertFrom-Json -AsHashtable -ErrorAction SilentlyContinue)
    if ($tft) {
      $filtered = @{}
      foreach ($k in $tft.Keys) { $filtered[$k] = @($tft[$k].Keys | Where-Object { $_ -match 'tft|Tft|TFT' }) }
      $filtered | ConvertTo-Json -Depth 4 | Set-Content "$out/lcu-help-tft.json"
    } else { Set-Content "$out/lcu-help-raw.txt" $help.Body }
    Log "League client API found; TFT endpoint list saved."
  } else { Log "League client API found but /help returned status $($help.Status)." }
} else { Log "League client UX not running or its API is not readable." }

# ---- poll loop ----
# Screenshots and polls run on separate clocks: polling (process scan, HTTP) is slow, and a
# scouted board or a reroll lasts only seconds, so screenshots must not wait on it.
$deadline = $start.AddMinutes($MaxMinutes)
$nextShot = Get-Date; $nextPoll = Get-Date
$game = $null; $gameSeen = $false; $gameGoneAt = $null; $phaseLast = $null
Log "Polling every $PollSeconds s, screenshots every $ShotSeconds s. Ctrl+C to stop."
try {
  while ((Get-Date) -lt $deadline) {
    if ($game -and (Get-Date) -ge $nextShot) {
      $nextShot = (Get-Date).AddSeconds($ShotSeconds)
      $shot = Save-Screenshot $game
      ([ordered]@{ t = (Get-Date).ToString('o'); shot = $shot } | ConvertTo-Json -Compress) | Add-Content "$out/poll.jsonl"
    }
    if ((Get-Date) -ge $nextPoll) {
      $nextPoll = (Get-Date).AddSeconds($PollSeconds)
      # Keep the known game process while it lives; rescan only when there is none.
      if (-not ($game -and (Get-Process -Id $game.Pid -ErrorAction SilentlyContinue))) { $game = Find-GameProcess }
      if ($game -and -not $gameSeen) { $gameSeen = $true; Log "Game process: $($game.Name) (pid $($game.Pid)) '$($game.WindowTitle)'"; Save-Env 'ingame' }
      if ($gameSeen -and -not $game) {
        if (-not $gameGoneAt) { $gameGoneAt = Get-Date; Log "Game process gone; stopping in $GraceSeconds s." }
        elseif (((Get-Date) - $gameGoneAt).TotalSeconds -gt $GraceSeconds) { break }
      } elseif ($game) { $gameGoneAt = $null }

      $line = [ordered]@{ t = (Get-Date).ToString('o'); game = $game.Name }
      $line.live = Poll-LiveClient
      if (-not $lcu) { $lcu = Get-Lcu }
      if ($lcu) {
        $ph = Invoke-Get "$($lcu.Base)/lol-gameflow/v1/gameflow-phase" $lcu.Headers
        $line.phase = $ph.Body
        $line.lcu_receipts = @(Save-LcuReceipts -Base $lcu.Base -Headers $lcu.Headers -Secrets $lcu.Secrets -OutputRoot (Join-Path $out 'lcu'))
        if ($ph.Body -ne $phaseLast) { $phaseLast = $ph.Body; Log "Client phase: $($ph.Body)" }
      }
      ($line | ConvertTo-Json -Depth 5 -Compress) | Add-Content "$out/poll.jsonl"
    }
    Start-Sleep -Milliseconds 200
  }
} finally {
  # The end record comes first: copying manual captures can take a while, and
  # closing the window before Done skips the rest of this block.
  Save-Env 'end'
  # Collect manual captures taken during the run.
  $pics = [Environment]::GetFolderPath('MyPictures')
  $vids = [Environment]::GetFolderPath('MyVideos')
  foreach ($dir in "$pics/Screenshots", "$vids/Captures") {
    if (Test-Path $dir) {
      Get-ChildItem $dir -File | Where-Object { $_.LastWriteTime -ge $start } |
        Copy-Item -Destination "$out/manual" -ErrorAction SilentlyContinue
    }
  }
  $shots = (Get-ChildItem "$out/shots" -File).Count
  $manual = (Get-ChildItem "$out/manual" -File).Count
  Log "Done. $shots auto screenshots, $manual manual captures. Output: $out"
}
