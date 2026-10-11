"""Capture policy and real adapters observed in fresh Python processes."""

import json
import os
import subprocess
import sys

import pytest


def test_reader_process_opts_out_before_runtime_initializes_and_still_reads():
    code = """
import json
import os
import sys

runtime_imports = []
def observe_import(event, args):
    if event == "import" and args[0].split(".")[0] == "onnxruntime":
        runtime_imports.append(os.environ.get("ORT_DISABLE_TELEMETRY"))
sys.addaudithook(observe_import)

from tft_capture.ocr import RapidOCRReader
from PIL import Image
reader = RapidOCRReader.from_bundled_models()
lines = reader.read(Image.new("RGB", (300, 120), "white"), region="process_fixture")
print("TFT_PROCESS_RESULT=" + json.dumps({
    "startup_opt_out": runtime_imports[0] if runtime_imports else None,
    "lines": len(lines),
}))
"""
    environment = dict(os.environ)
    environment.pop("ORT_DISABLE_TELEMETRY", None)
    process = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == 0, process.stderr
    result = next(
        json.loads(line.removeprefix("TFT_PROCESS_RESULT="))
        for line in process.stdout.splitlines()
        if line.startswith("TFT_PROCESS_RESULT=")
    )
    # ORT's documented full suppression is latched before uploader creation.
    assert result == {"startup_opt_out": "1", "lines": 0}


@pytest.mark.parametrize("command", ("tft-core", "tft-train"))
def test_cli_startup_opts_out_without_loading_optional_training_runtime(command):
    code = """
import json
import os
import sys
from importlib.metadata import entry_points

heavy_imports = []
def observe_import(event, args):
    if event == "import" and args[0].split(".")[0] in ("onnxruntime", "torch"):
        heavy_imports.append(args[0])
sys.addaudithook(observe_import)

command = sys.argv[1]
entry = next(iter(entry_points(group="console_scripts", name=command)))
main = entry.load()
print("TFT_PROCESS_RESULT=" + json.dumps({
    "startup_opt_out": os.environ.get("ORT_DISABLE_TELEMETRY"),
    "heavy_imports": heavy_imports,
}), flush=True)
sys.argv = [command, "--help"] if command == "tft-train" else [command]
main()
"""
    environment = dict(os.environ)
    environment.pop("ORT_DISABLE_TELEMETRY", None)
    environment.pop("TFT_CORE_TOKEN", None)
    process = subprocess.run(
        [sys.executable, "-c", code, command],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    result = next(
        json.loads(line.removeprefix("TFT_PROCESS_RESULT="))
        for line in process.stdout.splitlines()
        if line.startswith("TFT_PROCESS_RESULT=")
    )
    assert result == {"startup_opt_out": "1", "heavy_imports": []}
    if command == "tft-core":
        # The public CLI rejects an unlaunched core without reading owner data.
        assert process.returncode == 1
        assert "TFT_CORE_TOKEN is not set" in process.stderr
    else:
        assert process.returncode == 0, process.stderr
        assert "prepare-models" in process.stdout
