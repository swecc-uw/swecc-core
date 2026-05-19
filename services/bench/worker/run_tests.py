#!/usr/bin/env python
"""Test runner for bench-worker."""
from __future__ import annotations

import sys
from pathlib import Path

_WORKER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_WORKER_DIR.parent))

from test_support.env import apply_worker_env
from test_support.runner import run_service_tests

def _configure() -> None:
    apply_worker_env()


if __name__ == "__main__":
    sys.exit(run_service_tests(_WORKER_DIR, configure=_configure))
