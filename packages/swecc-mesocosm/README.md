# swecc-mesocosm

CLI and Python client for the BenchAnything benchmark/eval platform.

A *mesocosm* is a small, enclosed environment used for controlled experiments — which is exactly what this tool helps you build, register, and run evals against.

## Install

```bash
pip install swecc-mesocosm
# or, with uv:
uv tool install swecc-mesocosm
# or, with pipx:
pipx install swecc-mesocosm
```

For local development against this monorepo:

```bash
pip install -e ./packages/swecc-mesocosm
```

## Configure

The CLI reads `MESOCOSM_BASE_URL` from the environment (default: `http://127.0.0.1:8000`). You can also pass `--base-url` to any command.

```bash
export MESOCOSM_BASE_URL=http://127.0.0.1:8010   # docker compose
# or
export MESOCOSM_BASE_URL=https://api.swecc.org/bench
```

## Commands

```bash
mesocosm --help

# inference + validation (no network)
mesocosm suggest "Wordle clone where the agent gets 6 guesses."
mesocosm validate ./my-domain.json

# domain CRUD
mesocosm register --id my-bench --name "My Bench" --owner-id me \
  --description "Trivia about Python." --env-url https://envs.example.com/mybench
mesocosm publish my-bench
mesocosm get my-bench --artifacts
mesocosm list --status published

# evals
mesocosm eval test --domain-id my-bench --vow-version 1.0.0 --model openai/gpt-4o-mini
mesocosm eval run  --domain-id my-bench --vow-version 1.0.0 --model openai/gpt-4o-mini \
  --num-episodes 20 --seed-set '[1,2,3]'

# results
mesocosm run get <run-id>
mesocosm run episodes <run-id> --traces
```

All commands print JSON to stdout (pretty when stdout is a TTY, compact otherwise), so they pipe cleanly into `jq`:

```bash
mesocosm list --status published | jq '.benchmarks[].id'
```

## Python client

```python
import asyncio
from swecc_mesocosm import BenchAnythingClient

async def main():
    c = BenchAnythingClient(base_url="http://127.0.0.1:8000")
    try:
        domains = await c.list_domains(published_only=True)
        print(len(domains), "published")
    finally:
        await c.aclose()

asyncio.run(main())
```

## Policy / constraints

`mesocosm validate` reads `swecc_mesocosm/policy/constraints.json` shipped with the package — required register fields, allowed model prefixes, etc. Edit that file (or fork the package) to tune for your event.
