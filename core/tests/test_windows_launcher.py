"""Exercise the public launcher with external package-manager stand-ins."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


POWERSHELL = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="PowerShell 7 is required")
LAUNCHER = Path(__file__).resolve().parents[2] / "start.ps1"


def launch(tmp_path, *, fail="", installed=False):
    repo = tmp_path / "repo with spaces"
    repo.mkdir()
    shutil.copy2(LAUNCHER, repo / "start.ps1")
    (repo / "core").mkdir()
    (repo / "ui").mkdir()
    if installed:
        (repo / "ui" / "node_modules").mkdir()
    commands = tmp_path / "commands"
    commands.mkdir()
    log = tmp_path / "calls.jsonl"
    helper = commands / "command.py"
    helper.write_text('''import json, os, sys
command, *args = sys.argv[1:]
phase = "sync" if command == "uv" else ("install" if args[0] == "ci" else args[-1])
with open(os.environ["LAUNCHER_CALLS"], "a") as out:
    out.write(json.dumps({"phase": phase, "args": args}) + "\\n")
sys.exit(23 if phase == os.environ.get("LAUNCHER_FAIL") else 0)
''')
    for command in ("uv", "npm"):
        if os.name == "nt":
            executable = commands / f"{command}.cmd"
            executable.write_text(f'@"{sys.executable}" "{helper}" {command} %*\r\n@exit /b %errorlevel%\r\n')
        else:
            executable = commands / command
            executable.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{helper}" {command} "$@"\n')
            executable.chmod(0o755)
    env = os.environ | {
        "PATH": str(commands) + os.pathsep + os.environ["PATH"],
        "LAUNCHER_CALLS": str(log), "LAUNCHER_FAIL": fail,
    }
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-File", str(repo / "start.ps1")],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    return result, calls, repo


def test_fresh_checkout_builds_before_start_from_any_working_directory(tmp_path):
    result, calls, repo = launch(tmp_path)
    assert result.returncode == 0, result.stderr
    assert [call["phase"] for call in calls] == ["sync", "install", "build", "start"]
    assert len(calls[0]["args"]) == 4
    assert calls[0]["args"][:2] == ["sync", "--project"]
    assert Path(calls[0]["args"][2]) == repo / "core"
    assert calls[0]["args"][3] == "--quiet"
    assert len(calls[1]["args"]) == 3
    assert calls[1]["args"][:2] == ["ci", "--prefix"]
    assert Path(calls[1]["args"][2]) == repo / "ui"
    for call, phase in zip(calls[2:], ["build", "start"]):
        assert len(call["args"]) == 4
        assert call["args"][0] == "--prefix"
        assert Path(call["args"][1]) == repo / "ui"
        assert call["args"][2:] == ["run", phase]


@pytest.mark.parametrize("fail,expected", [
    ("sync", ["sync"]),
    ("install", ["sync", "install"]),
    ("build", ["sync", "install", "build"]),
    ("start", ["sync", "install", "build", "start"]),
])
def test_failed_stage_preserves_exit_code_and_stops_workflow(tmp_path, fail, expected):
    result, calls, _ = launch(tmp_path, fail=fail)
    assert result.returncode == 23, result.stderr
    assert [call["phase"] for call in calls] == expected


def test_existing_dependencies_still_rebuild_before_start(tmp_path):
    result, calls, _ = launch(tmp_path, installed=True)
    assert result.returncode == 0, result.stderr
    assert [call["phase"] for call in calls] == ["sync", "build", "start"]
