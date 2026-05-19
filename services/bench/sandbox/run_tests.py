#!/usr/bin/env python
"""Test runner for bench-sandbox."""
from __future__ import annotations

import sys
from pathlib import Path

_SANDBOX_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SANDBOX_DIR.parent))

from test_support.env import apply_sandbox_env
from test_support.runner import run_service_tests

def _configure() -> None:
    apply_sandbox_env()


if __name__ == "__main__":
    sys.exit(run_service_tests(_SANDBOX_DIR, configure=_configure))
