# BenchAnything — Onboarding Guide

This guide covers everything a team needs to go from zero to a running benchmark
in one session: local dev setup, authoring an environment, submitting it, and
reading results.

---

## Contents

1. [What is BenchAnything?](#1-what-is-benchanything)
2. [Local dev — quick start with SQLite](#2-local-dev--quick-start-with-sqlite)
3. [Authoring a benchmark environment](#3-authoring-a-benchmark-environment)
4. [The benchanything.json manifest](#4-the-benchanythingjson-manifest)
5. [Submitting via API](#5-submitting-via-api)
6. [Submitting via GitHub](#6-submitting-via-github)
7. [Running a dev test bench](#7-running-a-dev-test-bench)
8. [Triggering a full bench](#8-triggering-a-full-bench)
9. [Reading results](#9-reading-results)
10. [Error reference](#10-error-reference)
11. [Architecture overview](#11-architecture-overview)

---

## 1. What is BenchAnything?

BenchAnything is a platform where teams expose an *environment* (a task the agent
must solve) over a simple HTTP interface, and the platform runs five canonical AI
models against it.  Results appear on a leaderboard.

Key concepts:

| Term | Meaning |
|------|---------|
| **Domain** | A benchmark specification: spaces, reward, scoring config, and a running env |
| **BindingVow** | The typed contract (observation space, action space, reward) pinned to a SemVer |
| **Episode** | One full run of an agent through the environment (reset → step… → done) |
| **Run** | A batch of episodes for one model against one domain |
| **BenchJob** | A queued request to run all five models against one env (full bench) |

---

## 2. Local dev — quick start with SQLite

The full Docker stack needs Postgres.  For local iteration you can run without it:

```bash
# In services/bench/
ORCH_DB_BACKEND=sqlite ORCH_SQLITE_PATH=./bench_dev.db \
    uvicorn app.main:app --reload --port 8010
```

SQLite tables are created automatically on first startup — no migration step.

To run the inference CLI against a locally running adapter:

```bash
ORCH_DB_BACKEND=sqlite ORCH_SQLITE_PATH=./bench_dev.db \
    python -m bench_common.inference.bench \
        --model ollama/llama3.2 \
        --domain my-domain-id \
        --env-url http://localhost:9000 \
        --episodes 5
```

For the full Docker stack (Postgres):

```bash
# From swecc-core root
cp .env.example .env   # fill in DB_*, ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.
docker compose up bench-api bench-sandbox bench-worker
```

The API is then at `http://localhost:8010`.  Interactive docs: `http://localhost:8010/docs`.

---

## 3. Authoring a benchmark environment

An environment is a Git repository with at least two files:

```
my-benchmark/
├── benchanything.json   ← manifest (required)
├── adapter.py           ← HTTP server that the platform calls
└── requirements.txt     ← Python deps for the adapter (optional)
```

Start from the scaffold:

```bash
cp -r services/bench/template/ my-benchmark/
cd my-benchmark/
```

### The adapter contract

The platform calls three endpoints on your adapter:

| Endpoint | Body | Response |
|----------|------|----------|
| `POST /reset` | `{"episode_id": "...", "seed": 42}` | `{"data": <obs>, "system_prompt": "..."}` |
| `POST /step`  | `{"episode_id": "...", "action": <act>}` | `{"observation": {"data": <obs>}, "reward": 1.0, "terminated": true, "truncated": false, "info": {}}` |
| `POST /close` | `{"episode_id": "..."}` | `{}` |
| `GET  /health` | — | `{"status": "ok"}` |

Use the SDK helper to remove boilerplate:

```python
# adapter.py
import argparse
from bench_common.env_sdk.base import BaseEnv, StepResult
from bench_common.env_sdk.server import serve   # serves the four endpoints above

class MyEnv(BaseEnv):
    def reset(self, seed=None, **_):
        self.answer = "Paris"
        return {"question": "What is the capital of France?"}

    def step(self, action):
        correct = str(action).strip().lower() == self.answer.lower()
        return StepResult(
            observation={"question": ""},
            reward=1.0 if correct else 0.0,
            terminated=True,
            truncated=False,
            info={"correct": str(correct)},
        )

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=9000)
    serve(MyEnv, port=p.parse_args().port)
```

Test it locally before submitting:

```bash
python adapter.py --port 9000 &
curl http://localhost:9000/health          # → {"status":"ok"}
curl -X POST http://localhost:9000/reset \
     -H "Content-Type: application/json" \
     -d '{"episode_id":"e1","seed":0}'
```

---

## 4. The benchanything.json manifest

The manifest declares your environment's contract.  Every field that is not
optional is required — the platform rejects submissions with missing or malformed
manifests and returns a 422 with the specific field that failed.

```jsonc
{
  "adapter": "adapter.py",           // filename of the HTTP adapter script
  "name": "My Benchmark",            // display name
  "description": "What agents do.",

  "binding_vow": {
    "version": "1.0.0",              // SemVer — bump MINOR/MAJOR on breaking changes
    "tier": "tier1",                 // "tier1" (standard) | "tier2" (extended)
    "description": "Agent task description shown to the model as system context.",

    "observation_space": {
      "type": "json",                // discrete | continuous | text | json | image | composite
      "description": "{ \"question\": string }"
    },

    "action_space": {
      "type": "discrete",
      "enum_values": ["A", "B", "C", "D"],
      "description": "Single letter answer"
    },

    "reward": {
      "type": "binary",              // scalar | vector | sparse | binary
      "range": { "low": 0.0, "high": 1.0 },
      "description": "1.0 if correct, 0.0 otherwise"
    },

    "episode": {
      "max_steps": 1,                // null = unlimited
      "max_wall_seconds": null,      // null = no wall-clock limit
      "deterministic_reset": true,
      "supports_seed": true,
      "parallel_episodes": 1,        // how many episodes this adapter can handle in parallel
      "observability": "full"        // "full" | "partial"
    },

    "techniques": []                 // technique declarations — leave empty for basic envs
  },

  "scoring": {
    "primary_metric": "accuracy",   // must match one of the metrics below
    "higher_is_better": true,
    "metrics": [
      {
        "name": "accuracy",
        "type": "episode_reward",    // episode_reward | terminal_field | trajectory_judge
        "aggregation": "pass_rate"   // mean | median | max | min | sum | pass_rate
      }
    ]
  }
}
```

### Common mistakes

| Symptom | Likely cause |
|---------|-------------|
| 422 "missing required key" | Forgot `adapter`, `name`, `binding_vow`, or `scoring` |
| 422 "discrete space must declare enum_values" | `type: "discrete"` but no `enum_values` list |
| 422 "is not valid SemVer" | `version: "v1"` — must be `"1.0.0"` |
| 422 "reward.range.low must be < high" | `low` ≥ `high` in the range object |
| 502 "Adapter exited… before /health responded" | Crash at startup — check adapter stderr |
| 502 "did not respond to GET /health within 30 s" | Adapter not calling `serve()` or not accepting `--port` |

---

## 5. Submitting via API

If you have a running adapter and want to register it directly:

```bash
curl -X POST http://localhost:8010/v1/domains \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my-benchmark-v1",
    "name": "My Benchmark",
    "owner_id": "your-user-id",
    "binding_vow": { ... },
    "endpoint": { "mode": "remote", "url": "http://my-adapter-host:9000" },
    "scoring": { ... }
  }'
```

---

## 6. Submitting via GitHub

Push your env repo to GitHub, then submit the URL:

```bash
curl -X POST http://localhost:8010/v1/developer/environments \
  -H "Content-Type: application/json" \
  -d '{
    "owner_id": "your-user-id",
    "name": "My Benchmark",
    "github_url": "https://github.com/your-org/my-benchmark"
  }'
```

Response includes an `id` and `status: "pending"`.  Poll for readiness:

```bash
curl http://localhost:8010/v1/developer/environments/{id}/poll
```

Status transitions:

```
pending → cloning → ready
                  → failed  (check error_message in response)
```

If onboarding fails, fix the repo and retry without re-submitting:

```bash
curl -X POST http://localhost:8010/v1/developer/environments/{id}/retry
```

---

## 7. Running a dev test bench

A dev test bench runs **one model, one episode at a time** against your env.
Use this to verify correctness before the full 5-model run.

```bash
curl -X POST http://localhost:8010/v1/bench/test \
  -H "Content-Type: application/json" \
  -d '{
    "env_id": "<your-env-id>",
    "model": "anthropic/claude-sonnet-4-6",
    "num_episodes": 1,
    "seed": 42
  }'
```

Check if a bench is currently running (only one at a time is allowed):

```bash
curl http://localhost:8010/v1/bench/status
# → {"busy": false}
```

You can also stream the episode trace in real-time via WebSocket:

```
ws://localhost:8010/v1/ws/episodes/{episode_id}/trace
```

---

## 8. Triggering a full bench

A full bench runs **all five canonical models** (Claude, GPT-4o, Gemini, DeepSeek, Grok-2)
with five episodes each (25 total) and saves results to the leaderboard.

```bash
curl -X POST http://localhost:8010/v1/bench/full/{env_id}
# → 202 Accepted with {"id": "<job_id>", "status": "queued", ...}
```

Poll job status:

```bash
curl http://localhost:8010/v1/bench/jobs/{job_id}
```

Status: `queued → running → completed | failed`

---

## 9. Reading results

### Leaderboard

```bash
curl http://localhost:8010/v1/leaderboard?domain_id={domain_id}
```

### Usage stats for your env

```bash
curl http://localhost:8010/v1/developer/environments/{env_id}/usage
# → {"total_runs": 12, "total_episodes": 60, "avg_score": 0.82, "best_score": 0.96, ...}
```

### Episode trace

```bash
# List runs for a domain
curl http://localhost:8010/v1/runs?domain_id={domain_id}

# Stream a specific episode's trace
wscat -c ws://localhost:8010/v1/ws/episodes/{episode_id}/trace
```

Trace events are JSONL:

```json
{"episode_id": "...", "step": 1, "event_type": "observation", "payload": {"data": {...}}}
{"episode_id": "...", "step": 1, "event_type": "action", "payload": {"action": "A"}}
{"episode_id": "...", "step": 1, "event_type": "step_result", "payload": {"reward": 1.0, "terminated": true}}
{"episode_id": "...", "step": 1, "event_type": "episode_end", "payload": {"total_reward": 1.0, "steps": 1}}
```

---

## 10. Error reference

All errors are JSON `{"detail": "..."}`.  The message is always actionable.

| HTTP status | Source | Meaning |
|-------------|--------|---------|
| 400 | API | Bad request — see `detail` |
| 404 | API | Resource not found |
| 409 | API | Conflict (domain exists, env already cloning/ready, job already claimed) |
| 422 | API / Sandbox | Manifest or vow validation failed — `detail` identifies the field |
| 429 | API | Dev test bench already running — wait and retry |
| 502 | Sandbox | Adapter subprocess crashed or failed health check — `detail` includes stderr tail |

### `VowViolationError` structure

```
BindingVow 'my-vow' (v1.0.0) has 2 violation(s):
  • action_space: discrete space must declare enum_values
  • episode.max_steps must be a positive integer when set
```

### `ManifestError` structure

```
benchanything.json is missing required key(s): 'binding_vow', 'scoring'
```

---

## 11. Architecture overview

```
┌───────────────���──────────────────────────────────────────┐
│                        bench-api :8010                   │
│  FastAPI  ·  Django/SQLite ORM  ·  WebSocket trace stream │
│                                                          │
│  routes/domains.py     — Domain CRUD                     │
│  routes/developer.py   — DeveloperEnvironment lifecycle  │
│  routes/bench.py       — test bench + full bench jobs    │
│  routes/runs.py        — Run / Episode inspection        │
│  routes/leaderboard.py — Leaderboard queries             │
└────────────┬─────────────────────────┬──────────────────��┘
             │ HTTP /clone             │ HTTP /v1/bench/jobs
             ▼                         ▼
┌────────────────────┐       ┌─────────────────────┐
│  bench-sandbox     │       │  bench-worker (EC2)  │
│  :8001             │       │  (polls + executes)  │
│                    │       │                      │
│  clones GitHub     │       │  git clone           │
│  repos, starts     │       │  pip install         │
│  adapter process,  │       │  start adapter       │
│  proxies /reset    │       │  bench all 5 models  │
│  /step /close      │       │  POST results        │
└───────���────────────┘       └─────────────────────┘

Storage backends (ORCH_DB_BACKEND):
  "django"  → shared Postgres via Django ORM  (production)
  "sqlite"  → local aiosqlite file            (local dev / EC2 worker)
```

Each run goes through:

```
submit env → sandbox clones + starts adapter → domain created
    → POST /v1/bench/test  OR  POST /v1/bench/full/{env_id}
    → orchestrator.create_run()
    → AgentLoop: reset → [decide → step]* → close
    → compute_scores()
    → leaderboard updated
```
