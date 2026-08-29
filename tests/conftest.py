"""Load the hyphenated ComfyUI custom-node package for isolated tests."""

from __future__ import annotations

import sys
import types
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "comfyui_flow_agent_under_test"


def pytest_sessionstart(session):
    # Register only the package namespace here. Individual tests import the
    # modules they exercise, so HTTP-only tests can run outside a ComfyUI/torch
    # environment while node/image tests still use ComfyUI's real torch.
    module = types.ModuleType(PACKAGE_NAME)
    module.__path__ = [str(PACKAGE_ROOT)]
    module.__package__ = PACKAGE_NAME
    sys.modules[PACKAGE_NAME] = module
