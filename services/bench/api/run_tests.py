#!/usr/bin/env python
"""Test runner for bench-api (pytest; setup in tests/conftest.py)."""
from __future__ import annotations

import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_API_DIR.parent))

from test_support.runner import run_service_tests  # noqa: E402

if __name__ == "__main__":
    sys.exit(
        run_service_tests(
            _API_DIR,
            extra_sys_path=[_API_DIR.parent.parent / "server" / "server"],
        )
    )
