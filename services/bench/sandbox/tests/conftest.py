"""
Pytest configuration for bench-sandbox tests.

Sets placeholder env vars before app imports (see ai/tests/conftest.py).
No database — sandbox only manages local env subprocesses.
"""

import pytest
from test_support.conftest_helpers import ensure_bench_root_on_path
from test_support.env import apply_sandbox_env

ensure_bench_root_on_path()
apply_sandbox_env()


@pytest.fixture(autouse=True)
def _isolated_envs_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVS_DIR", str(tmp_path / "envs"))
