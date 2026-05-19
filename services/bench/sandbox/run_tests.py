#!/usr/bin/env python
"""Test runner for bench-sandbox (pytest; setup in tests/conftest.py)."""
from __future__ import annotations

import sys
from pathlib import Path

_SANDBOX_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SANDBOX_DIR.parent))

from test_support.runner import run_service_tests  # noqa: E402

if __name__ == "__main__":
    sys.exit(run_service_tests(_SANDBOX_DIR))
