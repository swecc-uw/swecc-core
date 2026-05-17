# swecc-mesocosm

CLI and Python client for SWECC's benchmark and eval platform.

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
mesocosm list --status published | jq '.[].id'
```

## Local vs bench-api commands

**Local** means the CLI does not call bench-api at `MESOCOSM_BASE_URL` (no HTTP to `/v1/...`). That is not the same as “no LLM”: model calls happen on the **server** when you use `eval` commands.

**Bench-api** means the command needs a reachable bench-api (`MESOCOSM_BASE_URL` or `--base-url` on the command).

### Local (no bench-api)

| Command | What it does |
| --------| -------------|
| `mesocosm --version` / `-V` | Print the installed package version. |
| `mesocosm suggest <description>` | Regex heuristics on your text → JSON defaults (`benchmark_kind`, `scoring_source`, `max_steps`, `primary_metric`, `reasoning`, `tags`). Preview only; does not register. |
| `mesocosm validate <path>` | Check a domain JSON payload against shipped `policy/constraints.json` (`-` = stdin). Exit 0 if `ok`, else 1. |

These work without bench-api running.

### Bench-api (HTTP)

| Command | API | What it does |
| --------|-----| -------------|
| `mesocosm register` | `POST /v1/domains` (409 → `PATCH`) | Build or load a payload, optionally run local `validate`, then upsert a draft domain. |
| `mesocosm publish <id>` | `POST /v1/domains/{id}/publish` | Publish a domain; print artifact SHA-256 digests. |
| `mesocosm get <id>` | `GET /v1/domains/{id}` | Fetch a domain; `--artifacts` adds synthesized contract files locally. |
| `mesocosm list` | `GET /v1/domains` | List domains (`--status`, `--json` for raw output). |
| `mesocosm eval test` | `POST /v1/test/episode` | One test episode (model + env on the server). |
| `mesocosm eval run` | `GET` domain + `POST /v1/runs` | Full eval run with aggregated scores. |
| `mesocosm run get <run-id>` | `GET /v1/runs/{id}` (+ episodes) | Run status and aggregate scores. |
| `mesocosm run episodes <run-id>` | `GET /v1/runs/{id}/episodes` | Episode list; `--traces` fetches traces too. |

`register` is hybrid: inference and `validate` run locally; the upsert step needs bench-api.

```text
LOCAL                          BENCH-API
────────────────────────────   ─────────────────────────────────────
mesocosm --version             mesocosm register
mesocosm suggest "<desc>"      mesocosm publish <id>
mesocosm validate <file>       mesocosm get <id> [--artifacts]
                               mesocosm list [--status ...] [--json]
                               mesocosm eval test ...
                               mesocosm eval run ...
                               mesocosm run get <run-id>
                               mesocosm run episodes <run-id> [--traces]
```

## Python client

```python
import asyncio
from swecc_mesocosm import BenchClient

async def main():
    c = BenchClient(base_url="http://127.0.0.1:8000")
    try:
        domains = await c.list_domains(published_only=True)
        print(len(domains), "published")
    finally:
        await c.aclose()

asyncio.run(main())
```

## Policy / constraints

`mesocosm validate` reads `swecc_mesocosm/policy/constraints.json` shipped with the package — required register fields, allowed model prefixes, etc. Edit that file (or fork the package) to tune for your event.
