# Packaging: swecc-mesocosm (the only CLI)

**One PyPI package, one command: `mesocosm`.** Do not publish `swecc-bench`, `bench-common`, or a separate `bench` console script.

| What | Where |
|------|--------|
| **PyPI** | `pip install swecc-mesocosm` |
| **CLI entry point** | `mesocosm` only (`swecc_mesocosm.cli:main`) |
| **Env-author commands** | `mesocosm init`, `mesocosm run local`, `mesocosm auth …`, `mesocosm env submit`, … — implemented in `bench_common.cli`, dispatched from `swecc_mesocosm.bench_dispatch` |
| **Bench-api client commands** | `mesocosm doctor`, `mesocosm register`, `mesocosm eval …`, `mesocosm run get`, … — Typer in `swecc_mesocosm.cli` |
| **`bench_common` library** | `services/bench/common/` — bundled into the wheel (not a separate PyPI install) |

## `run` disambiguation

| Command | Handler |
|---------|---------|
| `mesocosm run local` / `create` / `export` | `bench_common` (env author) |
| `mesocosm run get` / `episodes` | Typer `run_app` (bench-api) |

## Monorepo dev

```bash
pip install -e ./packages/swecc-mesocosm
sh packages/swecc-mesocosm/scripts/stage-bench-common.sh   # before local wheel build
```

Server images still `pip install` `services/bench/common` as a library (no CLI script).

## Release

1. Bump `version` in `packages/swecc-mesocosm/pyproject.toml`.
2. Tag `swecc-mesocosm-vX.Y.Z` or run **Publish swecc-mesocosm to PyPI** (`workflow_dispatch`).

CI runs `scripts/stage-bench-common.sh` then `python -m build --wheel`.
