"""Shared pytest conftest setup for bench-* services."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_bench_root_on_path() -> None:
    bench_root = Path(__file__).resolve().parent.parent
    root = str(bench_root)
    if root not in sys.path:
        sys.path.insert(0, root)
