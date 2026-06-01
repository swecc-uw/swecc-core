# Arithmetic Problems -- Local Dev Guide

This env was scaffolded as a new-developer walkthrough for the mesocosm (BenchAnything) workflow.
It benchmarks LLM arithmetic reasoning: 10 problems per episode covering +, -, x, and /.

---

## How this env was built (onboarding replay)

### Step 1 -- Scaffold a new env

```bash
cd services/bench/workflow_testing
mesocosm init --dir .
# Wrote files/env.py, files/adapter.py, files/benchanything.json, requirements.txt, LOCAL_DEV.md
```

### Step 2 -- Edit the env

`files/env.py` was updated to implement `ArithmeticEnv`:
- `reset(seed)` -- generates 10 arithmetic problems deterministically, returns the first
- `step(action)` -- checks `action["answer"]`, advances to the next problem, terminates after 10
- All 4 operations appear every episode; division always produces a whole-number answer

`files/benchanything.json` was updated with:
- `action_space.type = "json"` with a `schema_ref` so Gemini/GPT/Claude use structured output
- `episode.max_steps = 10` matching the 10-problem design
- `scoring.primary_metric = "accuracy"` (mean episode reward across runs)

---

## One-time setup

```bash
pip install swecc-mesocosm   # installs CLI + bench_common + HTTP stack
```

No extra packages are needed -- the arithmetic env uses only the Python stdlib.

---

## Local dev loop (Ollama -- no API key required)

```bash
ollama pull llama3.2        # one-time model download
ollama serve                # ensure Ollama is running

cd services/bench/workflow_testing

# Option A -- automatic adapter (mesocosm starts files/adapter.py for you)
mesocosm run local --manifest files/benchanything.json --episodes 5

# Option B -- manual adapter
# Terminal 1:
python files/adapter.py     # -> http://localhost:8765/health
# Terminal 2:
mesocosm run local --manifest files/benchanything.json --episodes 5
```

> **Note:** `mesocosm run local` uses Ollama and falls back to heuristic action parsing
> (no structured outputs). Results are approximate -- validate with a cloud model before publishing.

### Smoke-test without an agent

```python
# Run from services/bench/workflow_testing/
import sys; sys.path.insert(0, "../../common")
from files.env import ArithmeticEnv

env = ArithmeticEnv()
obs = env.reset(seed=42)
print("First problem:", obs["problem"])

result = env.step({"answer": 19})
print("reward:", result.reward, "terminated:", result.terminated)
env.close()
```

---

## Submitting and running with Gemini (platform workflow)

Once local runs look correct, submit to the platform and bench with Gemini:

### 1. Authenticate

```bash
mesocosm auth login
# prompts for swecc.org username + password
```

### 2. Submit the env

Push this folder to a GitHub repo, then:

```bash
mesocosm env submit \
  --name "Arithmetic Problems" \
  --github-url https://github.com/<you>/<your-repo>
# The platform clones the repo, reads files/benchanything.json, registers a draft domain.
```

### 3. Wait for the env to be ready

```bash
mesocosm env list
# Look for status=ready and note the domain_id (e.g. math-arithmetic)
```

### 4. Create a Gemini bench run

```bash
mesocosm run create \
  --domain math-arithmetic \
  --vow-version 1.0.0 \
  --model gemini/gemini-3.1-flash-lite \
  --episodes 10
```

---

## Local platform run (Docker -- structured outputs, no cloud submit)

To test Gemini structured outputs locally without submitting:

```bash
# From swecc-core repo root:
docker compose up bench-api bench-sandbox bench-worker

# Run via the inference CLI inside the container:
docker compose run --rm bench-api python -m bench_common.inference.bench \
  --model gemini/gemini-3.1-flash-lite \
  --domain math-arithmetic \
  --env-url http://host.docker.internal:8765 \
  --episodes 5
```

Requires `GOOGLE_API_KEY` in the root `.env`.

---

## Checklist before publishing

- [x] `/reset` with same seed returns same first problem (deterministic)
- [x] `/step` terminates at exactly 10 steps
- [x] All `info` values are strings
- [x] `max_steps = 10` set in binding vow
- [x] `action_space.type = "json"` with valid `schema_ref`
- [ ] Tested with at least one cloud model (Gemini/GPT/Claude) for structured-output round-trip
- [ ] `mesocosm run create` returns `status: completed` for at least one run

Once all boxes are checked, publish the domain via the API:

```bash
# Get your token first:
mesocosm auth token

# Publish:
curl -X POST https://api.swecc.org/bench/v1/domains/math-arithmetic/publish \
  -H "Authorization: Bearer <token>"
```
