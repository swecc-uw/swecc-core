"""Run pytest for a bench-* service directory."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path


def _ensure_bench_root_on_path() -> Path:
    bench_root = Path(__file__).resolve().parent.parent
    bench_root_str = str(bench_root)
    if bench_root_str not in sys.path:
        sys.path.insert(0, bench_root_str)
    return bench_root


def run_service_tests(
    service_dir: Path,
    *,
    configure: Callable[[], None] | None = None,
    extra_sys_path: list[Path] | None = None,
) -> int:
    _ensure_bench_root_on_path()
    service_dir = service_dir.resolve()
    if str(service_dir) not in sys.path:
        sys.path.insert(0, str(service_dir))
    for path in extra_sys_path or []:
        resolved = str(path.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)

    os.chdir(service_dir)
    if configure is not None:
        configure()

    import pytest

    return pytest.main(["tests/", "-v", *sys.argv[1:]])
