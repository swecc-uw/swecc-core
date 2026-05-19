"""
Pytest configuration for bench-worker tests.

WORKER_API_URL is required at import time (see app/worker.py). Set placeholders
before collection, same pattern as server/run_tests.py env setdefaults.
"""

import sys
from pathlib import Path

import pytest

_BENCH_ROOT = Path(__file__).resolve().parents[2]
if str(_BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_BENCH_ROOT))

from test_support.env import apply_worker_env  # noqa: E402

apply_worker_env()


@pytest.fixture(autouse=True)
def _worker_test_env(monkeypatch):
    monkeypatch.setenv("WORKER_API_URL", "http://localhost:8000")
    monkeypatch.setenv("WORKER_POLL_INTERVAL", "10")
