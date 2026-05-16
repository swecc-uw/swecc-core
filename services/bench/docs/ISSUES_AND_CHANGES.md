# Issues Found & Changes Made

Audit date: 2026-04-12

---

## Issues Found

### 1. `env_client.close()` never called — env server leaks episode instances

**Severity:** Bug

**Where:** `src/runtime/agent_loop.py` — `AgentLoop.run_episode()`

**Problem:** After an episode finishes (terminated, truncated, timeout, or max_steps), the agent loop never calls `POST /close` on the environment server. In the env adapter server (`src/env_sdk/server.py`), each episode creates an env instance stored in `_episodes: dict[str, BaseEnv]`. That dict entry is only removed when `/close` is called. Since no one calls it, every episode's env instance persists in memory until the env server is restarted.

The `HttpEnvClient` has a `close(episode_id)` method (line 96), and the env server has a `/close` endpoint (line 144) — they just never get connected.

**Impact:** Memory leak on the env server proportional to the number of episodes run. For long-running benchmarks (hundreds/thousands of episodes), this could be significant depending on the env's memory footprint.

---

### 2. `/v1/test/episode` returns HTTP 202 but runs synchronously

**Severity:** Bug (incorrect HTTP semantics)

**Where:** `src/api/routes/test.py:20`

**Problem:** The endpoint is decorated with `status_code=202` (Accepted), which signals "your request was accepted and will be processed asynchronously." But the handler `await`s `orchestrator.run_test_episode(...)`, which runs the entire episode inline and only returns the response once it's done. The client gets a fully completed Episode, not a pending job handle.

Compare with `POST /v1/runs` in `src/api/routes/runs.py:12`, which correctly uses `status_code=202` because it fires `asyncio.create_task(...)` and returns immediately.

**Impact:** Clients that check the status code to decide polling behavior would be confused — they'd start polling for a result that's already in the response.

---

### 3. `_TECHNIQUE_REGISTRY` duplicated in two files

**Severity:** Design inconsistency

**Where:**
- `src/inference/bench.py:57-61`
- `src/orchestrator/service.py:31-35`

**Problem:** The exact same `_TECHNIQUE_REGISTRY` dict (mapping technique IDs to implementation classes) is defined independently in both files. If someone adds a new technique and only updates one file, the other silently ignores that technique.

---

### 4. `EpisodicMemoryTechnique` step counter drifts after window fills

**Severity:** Bug

**Where:** `src/techniques/memory.py:67`

**Problem:** The step number recorded in each history entry was computed as:
```python
step = len(self._window) + 1
```
But `self._window` is a `deque(maxlen=window_size)`. Once the window fills to `window_size` entries, `len()` stays constant. So the step numbers in the history plateau — step 11, 12, 13... all get labeled as `window_size + 1`. The agent sees incoherent history like:

```
Step 10: obs=... | action=... | reward=0.0
Step 11: obs=... | action=... | reward=1.0
Step 11: obs=... | action=... | reward=0.0   <-- wrong
Step 11: obs=... | action=... | reward=1.0   <-- wrong
```

---

## Changes Made

### Fix 1: Call `env_client.close()` at end of episode

**File:** `src/runtime/agent_loop.py`

Added `await env_client.close(episode_id=episode_id)` in a try/except block right after the main loop exits and before techniques run `on_episode_end`. The try/except ensures a failed close doesn't crash the episode — it logs a warning and continues.

---

### Fix 2: Change `/v1/test/episode` status code to 200

**File:** `src/api/routes/test.py`

Changed `status_code=202` to `status_code=200` on the `start_test_episode` route decorator.

---

### Fix 3: Centralize `TECHNIQUE_REGISTRY`

**Files:**
- `src/techniques/__init__.py` — now exports `TECHNIQUE_REGISTRY` as the single source of truth
- `src/inference/bench.py` — removed local `_TECHNIQUE_REGISTRY`, imports from `src.techniques`
- `src/orchestrator/service.py` — same, removed local copy

Adding a new technique now requires updating only `src/techniques/__init__.py`.

---

### Fix 4: Use absolute step counter in `EpisodicMemoryTechnique`

**File:** `src/techniques/memory.py`

Added `self._step_counter: int = 0` as an instance attribute. It's reset in `on_episode_start()` and `on_episode_end()`, and incremented in `after_action()` instead of using `len(self._window) + 1`. The history entries now record the correct absolute step number regardless of window rotation.

---

## Generalized `register.py`

### The problem

The current workflow requires every env package to include its own `register.py` script. Each one is nearly identical — import `DOMAIN_CONFIG` from the local `domain.py`, call `register_domain()`. That's boilerplate that scales with the number of environments.

### The approach

Instead of each env owning a register script, I created a single generic CLI at `src/env_sdk/register.py` that:

1. Takes a **path to any `domain.py`** as an argument
2. Dynamically imports it using `importlib.util`
3. Looks for the `DOMAIN_CONFIG` variable (a `DomainConfig` instance)
4. Calls `register_domain()` with it

The key design decision: **the env developer's `domain.py` file remains unchanged**. It still defines `DOMAIN_CONFIG` as before. What's removed is the per-env `register.py` wrapper.

### ID derivation

Two optional modes for overriding the domain ID without editing `domain.py`:

- `--auto-id` — derives the domain ID from the **parent folder name** of the `domain.py` file. So `envs/chess_puzzle/domain.py` becomes domain ID `chess_puzzle`. The binding vow's `id` and `domain_id` fields are updated to match.
- `--id <custom>` — explicit override.

If neither flag is passed, the ID from `DOMAIN_CONFIG` is used as-is.

### Usage

```bash
# Basic — uses whatever ID is in domain.py
uv run python -m src.env_sdk.register docs/examples/simple_trivia/domain.py

# Auto-derive ID from folder name ("simple_trivia")
uv run python -m src.env_sdk.register docs/examples/simple_trivia/domain.py --auto-id

# Explicit ID override
uv run python -m src.env_sdk.register docs/examples/simple_trivia/domain.py --id my-trivia

# Register + publish in one command
uv run python -m src.env_sdk.register docs/examples/simple_trivia/domain.py --publish

# Different API server
uv run python -m src.env_sdk.register docs/examples/simple_trivia/domain.py --api http://prod:8000
```

### What this means for env developers

**Before:** 4 files per env — `env.py`, `domain.py`, `adapter.py`, `register.py`

**After:** 3 files per env — `env.py`, `domain.py`, `adapter.py`. Registration is a platform-level command, not a per-env script. Existing per-env `register.py` files still work and don't need to be deleted.

### File created

`src/env_sdk/register.py` — generic registration CLI (runs as `python -m src.env_sdk.register`)
