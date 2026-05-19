"""
Pytest configuration for bench-sandbox tests.

Sets placeholder env vars before app imports (see ai/tests/conftest.py).
No database — sandbox only manages local env subprocesses.
"""

import sys
from pathlib import Path

import pytest

_BENCH_ROOT = Path(__file__).resolve().parents[2]
if str(_BENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_BENCH_ROOT))

from test_support.env import apply_sandbox_env  # noqa: E402

apply_sandbox_env()


@pytest.fixture(autouse=True)
def _sandbox_test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVS_DIR", str(tmp_path / "envs"))
    monkeypatch.setenv("SANDBOX_HOST", "localhost")
    monkeypatch.setenv("ORCH_TRACE_DIR", "/tmp/bench-traces")
    monkeypatch.setenv("ORCH_SANDBOX_URL", "http://localhost:8001")
