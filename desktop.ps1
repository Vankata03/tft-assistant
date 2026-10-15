# Configure the optional Windows shortcut and login startup using local preferences.
[CmdletBinding()]
param(
    [switch]$Plan,
    [switch]$DesktopShortcut,
    [ValidateSet('Keep', 'On', 'Off')][string]$StartAtLogin = 'Keep',
    [string]$PreferencesRoot = ''
)
$ErrorActionPreference = 'Stop'
if (-not $PreferencesRoot) {
    $PreferencesRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'tft-assistant/desktop'
}
$PreferencesRoot = [IO.Path]::GetFullPath($PreferencesRoot)
$preferencesFile = Join-Path $PreferencesRoot 'preferences.json'
$preferences = @{ schema_version = 1; start_at_login = $false; desktop_shortcut = $false }
if (Test-Path $preferencesFile) {
    $saved = Get-Content -Raw $preferencesFile | ConvertFrom-Json -AsHashtable
    $known = @('schema_version', 'start_at_login', 'desktop_shortcut', 'repository')
    foreach ($key in $saved.Keys) { if ($key -notin $known) { throw "Unknown desktop preference: $key" } }
    if ($saved.schema_version -isnot [long] -or $saved.schema_version -ne 1 -or $saved.start_at_login -isnot [bool] -or $saved.desktop_shortcut -isnot [bool]) {
        throw 'Invalid local desktop preferences'
    }
    $preferences = $saved
}
if ($StartAtLogin -ne 'Keep') { $preferences.start_at_login = $StartAtLogin -eq 'On' }
if ($DesktopShortcut) { $preferences.desktop_shortcut = $true }
$preferences.repository = $PSScriptRoot
$wrapper = Join-Path $PreferencesRoot 'launch.vbs'
$launcher = Join-Path $PSScriptRoot 'start.ps1'
$logFile = Join-Path $PreferencesRoot 'launch.log'
$exitFile = Join-Path $PreferencesRoot 'launch-exit-code.txt'
if ($Plan) {
    @{
        start_at_login = $preferences.start_at_login
        desktop_shortcut = $preferences.desktop_shortcut
        preferences_file = $preferencesFile
        launcher = $launcher
        wrapper = $wrapper
        failure_log = $logFile
        exit_code_file = $exitFile
        capture_settings_modified = $false
        console_visible = $false
    } | ConvertTo-Json
    exit 0
}
if (-not $IsWindows) { throw 'Shortcut and login configuration require Windows. Use -Plan to inspect the workflow.' }
$powerShell = (Get-Command pwsh -ErrorAction Stop).Source
if (-not (Test-Path $launcher)) { throw "Repository launcher not found: $launcher" }
New-Item -ItemType Directory -Path $PreferencesRoot -Force | Out-Null
function Quote-PowerShell([string]$value) { return "'" + $value.Replace("'", "''") + "'" }
function Quote-Vbs([string]$value) { return '"' + $value.Replace('"', '""') + '"' }
$command = '& ' + (Quote-PowerShell $launcher) + ' *> ' + (Quote-PowerShell $logFile) + '; exit $LASTEXITCODE'
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$hiddenCommand = '"' + $powerShell + '" -NoProfile -EncodedCommand ' + $encoded
# WScript has no console. Run waits for the repository launcher and preserves its
# failure code in a local file; a failed hidden launch opens a visible explanation.
$vbs = @"
Option Explicit
Dim shell, files, output, code
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
code = shell.Run($(Quote-Vbs $hiddenCommand), 0, True)
Set output = files.CreateTextFile($(Quote-Vbs $exitFile), True)
output.WriteLine CStr(code)
output.Close
If code <> 0 Then
    shell.Popup "TFT Assistant failed to start (exit " & code & "). See " & $(Quote-Vbs $logFile), 0, "TFT Assistant", 16
End If
WScript.Quit code
"@
Set-Content -Path $wrapper -Value $vbs -Encoding Unicode
$wscript = Join-Path $env:WINDIR 'System32/wscript.exe'
$shell = New-Object -ComObject WScript.Shell
if ($preferences.desktop_shortcut) {
    $shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'TFT Assistant.lnk'
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $wscript
    $shortcut.Arguments = '"' + $wrapper + '"'
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.Description = 'Start TFT Assistant from its checked repository build'
    $shortcut.Save()
}
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
if ($preferences.start_at_login) {
    New-Item -Path $runKey -Force | Out-Null
    New-ItemProperty -Path $runKey -Name 'TFT Assistant' -Value ('"' + $wscript + '" "' + $wrapper + '"') -PropertyType String -Force | Out-Null
} else {
    if (Test-Path $runKey) {
        $existing = Get-ItemProperty -Path $runKey -Name 'TFT Assistant' -ErrorAction SilentlyContinue
        if ($existing) { Remove-ItemProperty -Path $runKey -Name 'TFT Assistant' -ErrorAction Stop }
    }
}
$temporary = $preferencesFile + '.tmp'
$preferences | ConvertTo-Json | Set-Content -Path $temporary -Encoding utf8
Move-Item -Path $temporary -Destination $preferencesFile -Force
Write-Output "Desktop preferences saved: $preferencesFile"
