"""Run pytest for a bench-* service directory."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def run_service_tests(service_dir: Path, *, extra_sys_path: list[Path] | None = None) -> int:
    bench_root = Path(__file__).resolve().parent.parent
    for path in (bench_root, service_dir.resolve(), *(extra_sys_path or [])):
        resolved = str(path.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)

    os.chdir(service_dir)
    import pytest

    return pytest.main(["tests/", "-v", *sys.argv[1:]])
