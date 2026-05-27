"""Route env-author commands to bench_common (single mesocosm entry point)."""

from __future__ import annotations

from pathlib import Path

# Top-level mesocosm commands delegated to bench_common.cli
_BENCH_ROOT = frozenset({"auth", "team", "env", "init"})
# mesocosm run create|local|export → bench; mesocosm run get|episodes → typer run_app
_BENCH_RUN = frozenset({"create", "local", "export"})


def try_dispatch_bench(argv: list[str]) -> bool:
    """
    If argv is an env-author command, run bench_common.cli and return True.
    argv is sys.argv[1:] (after ``mesocosm``).
    """
    if not argv:
        return False

    from bench_common.cli.main import main as bench_main

    if argv[0] == "bench":
        bench_main(argv[1:] or None)
        return True

    if argv[0] in _BENCH_ROOT:
        bench_main(argv)
        return True

    if argv[0] == "run" and len(argv) > 1 and argv[1] in _BENCH_RUN:
        bench_main(argv)
        return True

    if (
        argv[0] == "register"
        and len(argv) > 1
        and (argv[1].endswith(".py") or Path(argv[1]).exists())
    ):
        bench_main(argv)
        return True

    return False
