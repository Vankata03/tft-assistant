import importlib

import pytest


@pytest.mark.parametrize(
    "name",
    ["tft_core", "tft_core.baseline", "tft_engine", "tft_engine.allowlist", "tft_capture", "tft_live", "tft_review", "tft_harness"],
)
def test_package_imports(name):
    importlib.import_module(name)
