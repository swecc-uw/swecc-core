# swecc-bench

CLI for BenchAnything environment authors: scaffold repos, run local Ollama evals, and talk to Mesocosm.

```bash
pip install swecc-bench
```

## Quick start

```bash
mkdir my-env && cd my-env
bench init

ollama pull llama3.2
python adapter.py          # terminal 1
bench run local            # terminal 2 — uses Ollama + benchanything.json
```

See `LOCAL_DEV.md` in your repo after `bench init` for the full loop.

## Commands

| Command | Description |
|---------|-------------|
| `bench init` | Scaffold `benchanything.json`, `adapter.py`, `env.py`, showcase |
| `bench run local` | Bench against your adapter via Ollama (no platform submit) |
| `bench auth login` | Member session for Mesocosm API |
| `bench env submit` | Onboard a GitHub repo |
| `bench run create` | Run on the platform (cloud models) |

## Local vs platform

- **Local (`bench run local`)** — Ollama on your machine only; no API keys.
- **Platform (`bench run create`)** — SWECC-hosted bench-api; models and billing on the server.

## Development (monorepo)

```bash
pip install -e services/bench/common
```
