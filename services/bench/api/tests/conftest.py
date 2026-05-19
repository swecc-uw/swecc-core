"""
Pytest configuration for bench-api tests.

Environment variables and the SQLite database override are applied before any
test module imports app.main (see ai/tests/conftest.py). Database setup follows
services/server/run_tests.py via tests.django_setup.
"""

import sys
from pathlib import Path

import pytest

_BENCH_ROOT = Path(__file__).resolve().parents[2]
if str(_BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_BENCH_ROOT))

from test_support.env import apply_common_env  # noqa: E402
from tests.django_setup import configure_django_for_tests  # noqa: E402

apply_common_env()
configure_django_for_tests()


@pytest.fixture(autouse=True)
def _bench_test_env(monkeypatch):
    """Keep bench test env stable per test (bot/ai-style monkeypatch fixture)."""
    monkeypatch.setenv("ORCH_TRACE_DIR", "/tmp/bench-traces")
    monkeypatch.setenv("ORCH_SANDBOX_URL", "http://localhost:8001")
    monkeypatch.setenv("WORKER_API_URL", "http://localhost:8000")
