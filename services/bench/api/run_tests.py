#!/usr/bin/env python
"""
Test runner for bench-api.

Uses SQLite instead of PostgreSQL, matching services/server/run_tests.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parent
_BENCH_ROOT = _API_DIR.parent
_SERVER_APP = _API_DIR.parent.parent / "server" / "server"
sys.path.insert(0, str(_BENCH_ROOT))

from test_support.runner import run_service_tests  # noqa: E402

from tests.django_setup import configure_django_for_tests  # noqa: E402


def _configure() -> None:
    from test_support.env import apply_common_env

    apply_common_env()
    configure_django_for_tests()


if __name__ == "__main__":
    sys.exit(
        run_service_tests(
            _API_DIR,
            configure=_configure,
            extra_sys_path=[_SERVER_APP],
        )
    )
