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
