# Packaging: swecc-mesocosm (the only PyPI CLI)

**Do not create or document a separate PyPI package** (e.g. `swecc-bench`, `bench-common` on PyPI).

| What | Where |
|------|--------|
| **PyPI install** | `pip install swecc-mesocosm` only |
| **`mesocosm` command** | `swecc_mesocosm.cli` — Typer CLI, bench-api HTTP (register, eval, doctor, …) |
| **`bench` command** | `bench_common.cli` — env author workflow (`bench init`, `bench run local`, auth, teams, submit) |
| **`bench_common` library** | `services/bench/common/` — vendored into the `swecc-mesocosm` wheel at build time |

## Monorepo dev

```bash
pip install -e ./packages/swecc-mesocosm
pip install -e ./services/bench/common   # optional; mesocosm wheel bundles bench_common for PyPI
```

## Release

1. Bump `version` in `packages/swecc-mesocosm/pyproject.toml`.
2. Tag `swecc-mesocosm-vX.Y.Z` or run **Publish swecc-mesocosm to PyPI** (`workflow_dispatch`).

CI runs `scripts/stage-bench-common.sh` before `python -m build` (copies `services/bench/common/bench_common` into the wheel). For a local wheel:

```bash
cd packages/swecc-mesocosm
sh scripts/stage-bench-common.sh
python -m build
```

The staged `bench_common/` directory is gitignored; never commit it.
