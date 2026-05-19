"""Placeholder env vars for bench-* pytest runs (see services/server/run_tests.py)."""

from __future__ import annotations

import os


def apply_common_env() -> None:
    os.environ.setdefault("ORCH_TRACE_DIR", "/tmp/bench-traces")
    os.environ.setdefault("ORCH_SANDBOX_URL", "http://localhost:8001")
    os.environ.setdefault("WORKER_API_URL", "http://localhost:8000")


def apply_sandbox_env() -> None:
    apply_common_env()
    os.environ.setdefault("ENVS_DIR", "/tmp/bench-envs")
    os.environ.setdefault("SANDBOX_HOST", "localhost")


def apply_worker_env() -> None:
    os.environ.setdefault("WORKER_API_URL", "http://localhost:8000")
    os.environ.setdefault("WORKER_POLL_INTERVAL", "10")
