"""The desktop workflow exposes a reviewable plan without changing host startup."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_desktop_plan_keeps_host_paths_out_of_capture_toml(tmp_path):
    powershell = shutil.which('pwsh')
    if powershell is None:
        pytest.skip('PowerShell 7 is required')
    script = Path(__file__).parents[2] / 'desktop.ps1'
    result = subprocess.run([powershell, '-NoProfile', '-File', str(script),
        '-Plan', '-PreferencesRoot', str(tmp_path / 'preferences with spaces'),
        '-StartAtLogin', 'On', '-DesktopShortcut'], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan['start_at_login'] is True
    assert plan['desktop_shortcut'] is True
    assert plan['capture_settings_modified'] is False
    assert Path(plan['launcher']) == script.parent / 'start.ps1'
    assert Path(plan['preferences_file']).parent == tmp_path / 'preferences with spaces'
    assert plan['console_visible'] is False
    assert not (tmp_path / 'preferences with spaces').exists()


def test_desktop_plan_rejects_unknown_local_preferences(tmp_path):
    powershell = shutil.which('pwsh')
    if powershell is None:
        pytest.skip('PowerShell 7 is required')
    script = Path(__file__).parents[2] / 'desktop.ps1'
    (tmp_path / 'preferences.json').write_text(json.dumps({
        'schema_version': 1, 'start_at_login': False, 'desktop_shortcut': False,
        'models': '/host/model-path',
    }))
    result = subprocess.run([powershell, '-NoProfile', '-File', str(script),
        '-Plan', '-PreferencesRoot', str(tmp_path)], capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'Unknown desktop preference' in result.stderr


def test_desktop_plan_rejects_boolean_schema_version(tmp_path):
    powershell = shutil.which('pwsh')
    if powershell is None:
        pytest.skip('PowerShell 7 is required')
    script = Path(__file__).parents[2] / 'desktop.ps1'
    (tmp_path / 'preferences.json').write_text(json.dumps({
        'schema_version': True, 'start_at_login': False, 'desktop_shortcut': False,
    }))
    result = subprocess.run([powershell, '-NoProfile', '-File', str(script),
        '-Plan', '-PreferencesRoot', str(tmp_path)], capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'Invalid local desktop preferences' in result.stderr


@pytest.mark.parametrize('launcher_exit', [0, 42])
def test_generated_hidden_payload_preserves_launcher_exit_status(tmp_path, launcher_exit):
    import re

    powershell = shutil.which('pwsh')
    if powershell is None:
        pytest.skip('PowerShell 7 is required')
    # External Windows shell/registry fixture; no actual host startup changes.
    repository = tmp_path / "repository with 'quotes'"
    repository.mkdir()
    script = repository / 'desktop.ps1'
    shutil.copyfile(Path(__file__).parents[2] / 'desktop.ps1', script)
    (repository / 'start.ps1').write_text(f"Write-Output 'fixture hidden launch'\nexit {launcher_exit}\n")
    preferences = tmp_path / "preferences with 'quotes'"
    driver = tmp_path / 'external-windows-shell.ps1'
    driver.write_text(r'''
param([string]$Script, [string]$PreferencesRoot)
Set-Variable -Name IsWindows -Value $true -Scope Global -Force
$env:WINDIR = $PreferencesRoot
function global:New-Object {
    param([string]$ComObject)
    if ($ComObject -ne 'WScript.Shell') { throw 'Unexpected external COM request' }
    return [PSCustomObject]@{}
}
function global:Test-Path {
    param([string]$Path)
    if ($Path.StartsWith('HKCU:')) { return $false }
    Microsoft.PowerShell.Management\Test-Path -LiteralPath $Path
}
& $Script -PreferencesRoot $PreferencesRoot
''')
    configured = subprocess.run([powershell, '-NoProfile', '-File', str(driver),
        '-Script', str(script), '-PreferencesRoot', str(preferences)],
        capture_output=True, text=True, timeout=10)
    assert configured.returncode == 0, configured.stderr
    wrapper = (preferences / 'launch.vbs').read_text(encoding='utf-16')
    encoded = re.search(r'-EncodedCommand ([A-Za-z0-9+/=]+)', wrapper)
    assert encoded is not None
    launched = subprocess.run([powershell, '-NoProfile', '-EncodedCommand', encoded.group(1)],
        capture_output=True, text=True, timeout=10)
    assert launched.returncode == launcher_exit, launched.stderr
    assert 'fixture hidden launch' in (preferences / 'launch.log').read_text(encoding='utf-8-sig')
