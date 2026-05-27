# BenchAnything — Environment Developer Onboarding

Welcome. This guide gets you from **zero to a published benchmark environment** in about 20 minutes.

---

## What is BenchAnything?

BenchAnything is a platform that sits between your RL environment and AI agent researchers. You own and run your environment. The platform handles:

- **Agent execution** — runs LLM-based agents against your env via LiteLLM
- **Protocol mediation** — a standard HTTP interface so any agent talks to any env
- **Tracing** — full logs of every observation, action, and reward
- **Scoring** — configurable metrics + leaderboard rankings
- **Reproducibility** — seed sets, binding vow versioning, trace replay

Your responsibility is small: run an HTTP server that speaks a four-endpoint protocol. The rest is handled.

---

## The Developer Flow

```
Your env server              Domain config             Running agents
───────────────              ─────────────             ──────────────
my_env_server.py             domain.py                 POST /v1/runs
  GET  /health               DomainConfig(               { agent_config,
  POST /reset     ◄────────    binding_vow,                domain_id }
  POST /step      ◄────────    scoring,
  POST /close     ◄────────    endpoint.url
                             )
        │                         │                       │
        │                         ▼                       │
        │                   register.py  ◄────────────────┘
        │                   register_domain(config)
        │
        ▼ platform agent runtime calls your server directly
```

**That's the whole contract.** Implement the four HTTP endpoints however you like — FastAPI, Flask, Express, a bare `http.server`. Language doesn't matter.

### Do you need the adapter module?

Only if you're wrapping a **3rd-party environment** (e.g. a Gymnasium env) and don't want to write the HTTP boilerplate yourself. In that case:

```python
# adapter.py — only needed for 3rd-party env wrapping
from src.env_sdk import BaseEnv, serve

class MyWrappedEnv(BaseEnv):
    def reset(self, seed=None, **kw): ...
    def step(self, action): ...

serve(MyWrappedEnv, port=8765)
```

If you're building your env from scratch, skip `BaseEnv` entirely and just implement the endpoints.

---

## Showcase in your own repo

Authors build demo UIs in **their** frontends using exported run JSON (`reasoning`, observations, actions). See **[SHOWCASE_DEVELOPER.md](./SHOWCASE_DEVELOPER.md)** for the full workflow (`mesocosm init`, `mesocosm run export`).

Mesocosm public replay: `GET /v1/runs/{id}/export` (no auth for `gallery_public` completed runs).

---

## Quick Start (5 minutes)

### 1. Install

```bash
git clone <this-repo>
cd BenchAnything
uv sync
```

### 2. Start the platform API server (terminal 1)

```bash
uv run uvicorn src.api.app:app --reload
# → http://localhost:8000/docs
```

### 3. Start your environment server (terminal 2)

This is just an HTTP server. Use whatever you like. Example with the included simple-trivia env:

```bash
uv run python docs/examples/simple_trivia/adapter.py
# → http://localhost:8765/health
```

### 4. Register your domain (once)

```bash
uv run python docs/examples/simple_trivia/register.py
# → domain 'simple-trivia' registered
```

### 5. Bench a model against it (Ollama)

```bash
# Make sure Ollama is running:  ollama serve
# Pull a model:                 ollama pull llama3.2

uv run python -m src.inference.bench \
    --model ollama/llama3.2 \
    --domain simple-trivia \
    --env-url http://localhost:8765 \
    --episodes 10
```

Or via the platform API if you want traces + leaderboard:

```bash
curl -s -X POST http://localhost:8000/v1/test/episode \
  -H "Content-Type: application/json" \
  -d '{
    "domain_id": "simple-trivia",
    "binding_vow_version": "1.0.0",
    "env_url": "http://localhost:8765",
    "agent_config": { "model": "ollama/llama3.2" }
  }'
```

---

## Environment Contract

The platform calls **four HTTP endpoints** on your server. That's the entire interface.

```
GET  /health
     → { "status": "ok" }

POST /reset
     body:     { "episode_id": "...", "seed": 42, ...scenario_params }
     response: { "data": <observation>, "content_type": "application/json" }

POST /step
     body:     { "episode_id": "...", "action": <action> }
     response: {
                 "observation": { "data": <obs>, "content_type": "application/json" },
                 "reward": 1.0,
                 "terminated": true,
                 "truncated": false,
                 "info": { "key": "value", ... }
               }

POST /close
     body:     { "episode_id": "..." }
     response: {}
```

**Observations and actions** can be any JSON-serialisable value: `str`, `int`, `float`, `dict`, `list`.
The Binding Vow describes the shape (for agents to understand the space) — the platform does not type-check at runtime.

**`info`** must be `dict[str, str]` (all values stringified). Use it to pass metrics you want scored (e.g. `"correct": "True"`).

---

## The Binding Vow

The Binding Vow is the machine-readable contract between your environment and agent developers. It tells agents:

- What observations look like (`observation_space`)
- What actions are valid (`action_space`)
- How rewards work (`reward`)
- Episode limits (`episode.max_steps`, `episode.max_wall_seconds`)
- Which Techniques are available (`techniques`)

### Space types

| `type`        | Use when…                                     |
|---------------|-----------------------------------------------|
| `"discrete"`  | Fixed set of named choices (A/B/C/D, move/shoot/wait) |
| `"text"`      | Free-form string                              |
| `"json"`      | Structured dict (describe schema in `description`) |
| `"image"`     | Pixel array (`shape`, `dtype` required)       |
| `"continuous"`| Float vector (`shape`, `bounds` required)     |
| `"composite"` | Mix of the above (use `CompositeSpace`)        |

### Reward types

| `type`    | Meaning                              |
|-----------|--------------------------------------|
| `"binary"`  | 0 or 1 (success / fail)            |
| `"sparse"`  | Most steps 0, non-zero at key events |
| `"scalar"`  | Any float, every step               |
| `"vector"`  | Multiple objectives                 |

---

## Scoring Configuration

Define what the leaderboard measures:

```python
ScoringConfig(
    primary_metric="success_rate",   # This column is used for ranking
    higher_is_better=True,
    metrics=[
        MetricDef(
            name="success_rate",
            type="terminal_field",   # Read a key from episode.terminal_info
            field="success",         # env sets info["success"] = "True"/"False"
            aggregation="pass_rate", # % of episodes where field is truthy
        ),
        MetricDef(
            name="avg_reward",
            type="episode_reward",   # Sum of all rewards in episode
            aggregation="mean",      # Mean across episodes in a Run
        ),
        MetricDef(
            name="avg_steps",
            type="terminal_field",
            field="steps",
            aggregation="mean",
        ),
    ],
)
```

### Metric types

| `type`             | Source                                             |
|--------------------|----------------------------------------------------|
| `episode_reward`   | `episode.total_reward` (sum of step rewards)       |
| `terminal_field`   | A string key in the `info` dict of the last step   |
| `trajectory_judge` | LLM judge over the full trace *(Phase 2)*          |
| `human_judge`      | Human rater queue *(Phase 2)*                      |

### Aggregations

`mean` · `median` · `max` · `min` · `sum` · `pass_rate` (% > 0)

---

## Techniques

Techniques are optional agent capabilities your env can opt into. Declare them in your Binding Vow:

```python
techniques=[
    TechniqueDeclaration(
        technique_id="tool_calling",
        version="^1.0",
        config_schema={"tools": ["search", "calculator"]},
    ),
    TechniqueDeclaration(
        technique_id="memory",
        version="^1.0",
        config_schema={"window_size": 10},
    ),
]
```

Built-in techniques:

| ID             | What it does                                                    |
|----------------|-----------------------------------------------------------------|
| `tool_calling` | Injects tool definitions into the agent's system prompt         |
| `memory`       | Sliding window of recent steps + summary injected into prompt   |
| `multi_agent`  | Role-based prompt injection for multi-agent scenarios           |

---

## File Layout for Your Env Package

```
my_env/
├── env.py          # Your BaseEnv subclass — the actual environment logic
├── domain.py       # DomainConfig — metadata, binding vow, scoring
├── adapter.py      # 2 lines: import + serve(MyEnv, port=8765)
└── register.py     # 3 lines: import + register_domain(config)
```

See `docs/examples/simple_trivia/` for a complete working copy.

---

## Testing Your Environment

### Smoke test without an agent

```python
from my_env.env import MyEnv

env = MyEnv()
obs = env.reset(seed=42)
print("initial obs:", obs)

result = env.step("A")
print("reward:", result.reward, "terminated:", result.terminated)
env.close()
```

### End-to-end test via the platform

```bash
uv run python scripts/run_local_episode.py
```

Or use the `/v1/test/episode` API endpoint (see Quick Start above).

### Inspecting traces

```bash
# After a platform run (bench-api volume ORCH_TRACE_DIR, default ./data/traces)
cat data/traces/<episode-id>.jsonl | python -m json.tool | head -60

# Export a full showcase bundle (member auth or public gallery run):
mesocosm run export <run_id> -o replay.json
```

API:
```
GET /v1/runs/{run_id}/export   # run + episodes + traces + replay turns (with reasoning)
GET /v1/runs/{run_id}/traces   # raw trace map only
```

---

## Versioning

- The Binding Vow is **immutable once a Run references it**.
- To update your env contract, create a new Binding Vow with a bumped `version`.
- Use SemVer: `"1.0.0"` → `"1.1.0"` for backwards-compatible additions, `"2.0.0"` for breaking changes.
- `domain.id` stays the same; `binding_vow.id` and `binding_vow.version` change.

---

## Checklist Before Publishing

- [ ] `/reset` with the same `seed` returns the same initial observation (deterministic)
- [ ] `/step` eventually returns `"terminated": true` or `"truncated": true`
- [ ] All `info` values are strings (not ints, bools, or nested objects)
- [ ] `binding_vow.episode.max_steps` is set to prevent runaway episodes
- [ ] At least one `MetricDef` of type `terminal_field` or `episode_reward` is defined
- [ ] Domain registered and `/v1/test/episode` returns `status: "completed"`

Once the checklist passes, call `publish_domain()` (or `POST /v1/domains/{id}/publish`) to freeze the Binding Vow and enable leaderboard submissions.

---

## Reference

### Core (always relevant)

| File | Purpose |
|------|---------|
| [src/core/binding_vow.py](../src/core/binding_vow.py) | Full `BindingVow` schema |
| [src/core/scoring.py](../src/core/scoring.py) | `ScoringConfig` + `MetricDef` |
| [src/env_sdk/registration.py](../src/env_sdk/registration.py) | `register_domain()` / `publish_domain()` |

### Inference / benchmarking

| File | Purpose |
|------|---------|
| [src/inference/bench.py](../src/inference/bench.py) | `bench()` — run a model against a domain, print results |

CLI: `uv run python -m src.inference.bench --model ollama/llama3.2 --domain <id> --env-url <url>`

### 3rd-party env adapter (optional)

Only needed if you're wrapping an existing env (Gymnasium, etc.) and don't want to write the HTTP endpoints yourself.

| File | Purpose |
|------|---------|
| [src/env_sdk/base.py](../src/env_sdk/base.py) | `BaseEnv` ABC + `StepResult` dataclass |
| [src/env_sdk/server.py](../src/env_sdk/server.py) | `serve(MyEnv, port=8765)` — HTTP adapter server |
| [docs/examples/gym_adapter.py](examples/gym_adapter.py) | Wrapping a Gymnasium env in one class |

### Examples

| File | Purpose |
|------|---------|
| [docs/examples/simple_trivia/](examples/simple_trivia/) | Complete worked example (4 files) |
| [docs/examples/game_2048/](examples/game_2048/) | 2048 (4x4) slide-and-merge game |
