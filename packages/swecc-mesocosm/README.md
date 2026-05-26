# swecc-mesocosm

CLI and Python client for SWECC's BenchAnything / Mesocosm platform.

```bash
pip install swecc-mesocosm
mesocosm --help
```

**One package, one command (`mesocosm`).** There is no separate `bench` binary or `swecc-bench` on PyPI.

## Env author quick start

```bash
mkdir my-env && cd my-env
mesocosm init

ollama pull llama3.2
python adapter.py          # terminal 1
mesocosm run local         # terminal 2 — Ollama + benchanything.json, no submit
```

When ready for the platform: `mesocosm auth login` → `mesocosm env submit` (creates the domain from `benchanything.json` in your repo) → `mesocosm run create` with the returned `domain_id`. See `LOCAL_DEV.md` in your repo after `mesocosm init`. You do **not** need `mesocosm register domain.py` for this flow.

## Command overview

| Area | Examples |
|------|----------|
| **Local env / Ollama** | `mesocosm init`, `mesocosm run local` |
| **Auth & teams** | `mesocosm auth login`, `mesocosm team create` |
| **Submit repo** | `mesocosm env submit --github-url …` |
| **Platform runs** | `mesocosm run create`, `mesocosm run export RUN_ID` |
| **Domain helpers** | `mesocosm suggest`, `mesocosm validate`, `mesocosm register` (API JSON/flags; legacy `register domain.py` only if your repo has `DOMAIN_CONFIG`) |
| **Bench-api eval** | `mesocosm doctor`, `mesocosm eval test`, `mesocosm run get` |

See `PACKAGING.md` in this directory for how `bench_common` is bundled and how `mesocosm run` routes local vs platform subcommands.

## Install (dev)

```bash
pip install -e ./packages/swecc-mesocosm
```

## Configure

```bash
mesocosm doctor                    # checks https://api.swecc.org/bench (default)
mesocosm doctor --local            # checks adapter :8765 + local bench-api :8010
export MESOCOSM_LOCAL=1            # same local profile for all commands
```

Remote defaults: `https://api.swecc.org/bench` and `https://api.swecc.org` for auth. Local: see `infra/mesocosm.env.example`.

## Python client

```python
import asyncio
from swecc_mesocosm import BenchClient

async def main():
    c = BenchClient(base_url="http://127.0.0.1:8010")
    try:
        domains = await c.list_domains(published_only=True)
        print(len(domains), "published")
    finally:
        await c.aclose()

asyncio.run(main())
```
