"""
Pytest configuration for bench-worker tests.

WORKER_API_URL is required at import time (see app/worker.py). Set placeholders
before collection, same pattern as server/run_tests.py env setdefaults.
"""

from test_support.conftest_helpers import ensure_bench_root_on_path
from test_support.env import apply_worker_env

ensure_bench_root_on_path()
apply_worker_env()
