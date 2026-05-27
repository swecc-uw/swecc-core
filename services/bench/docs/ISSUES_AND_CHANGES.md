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

---

# Audit 2 — May 2026

---

## Issues Found

### 5. `env_client.close()` never called on exception or timeout

**Severity:** Critical

**Where:** `bench_common/runtime/agent_loop.py`

**Problem:** `env_client.close()` was called after the `while True:` episode loop in a standalone `try/except`. Any unhandled exception (timeout, inference error, env error) would skip the `close()` call, leaving the episode instance alive on the env server forever. `asyncio.CancelledError` — a `BaseException` since Python 3.8 — was also not caught, so task cancellation silently leaked instances.

**Fix:** Wrapped the entire `while True:` loop in a `try/finally` block so `close()` is called regardless of how the loop exits.

---

### 6. Run stays "completed" when all episodes failed

**Severity:** Critical

**Where:** `bench_common/orchestrator/service.py` — `_run_all_episodes()`

**Problem:** After all episodes finished, the orchestrator called `compute_scores()` and set `run.status = "completed"` regardless of episode outcomes. A run where every episode failed would appear on the leaderboard with a score of 0.0 — a crash misrepresented as a legitimate zero score.

**Fix:** Added an early-return check: if every episode has `status == "failed"`, the run is marked `"failed"` and `compute_scores` is skipped.

---

### 7. `run_test_episode()` does not handle `asyncio.CancelledError`

**Severity:** Critical

**Where:** `bench_common/orchestrator/service.py` — `run_test_episode()`

**Problem:** The outer `except Exception` block does not catch `asyncio.CancelledError` (a `BaseException`). If the task was cancelled while the episode was running, the episode and run would stay permanently in `"running"` status in the database.

**Fix:** Added an explicit `except asyncio.CancelledError` handler that marks both the episode and run as `"cancelled"` before re-raising.

---

### 8. `/jobs/{job_id}/claim` endpoint missing authentication

**Severity:** Critical

**Where:** `bench-api/app/routes/bench.py`

**Problem:** The `PATCH /jobs/{job_id}/claim` endpoint had no authentication dependency. Any unauthenticated client could claim — and effectively hijack — queued benchmark jobs.

**Fix:** Added `dependencies=[Depends(require_worker)]` to the route decorator.

---

### 9. Binding vow version regexes not anchored

**Severity:** Serious

**Where:** `bench_common/core/binding_vow.py`

**Problem:** `_SEMVER_RE` and `_VERSION_REQ_RE` lacked `$` end anchors. Strings like `"1.0.0-beta"` or `"1.0.0 injected"` would silently pass validation.

**Fix:** Added `$` to both compiled patterns: `r"^\d+\.\d+\.\d+$"` and `r"^[\^~]?\d+\.\d+(\.\d+)?$"`.

---

### 10. `RunConfig` accepts contradictory `seed_set` / `num_episodes`

**Severity:** Serious

**Where:** `bench_common/core/run.py`

**Problem:** Nothing stopped callers from passing `seed_set=[1, 2, 3]` with `num_episodes=10`. The orchestrator would silently use the seed list and create 3 episodes instead of 10, making the run look partially executed.

**Fix:** Added a Pydantic `@model_validator(mode="after")` that raises `ValueError` when `seed_set is not None and len(seed_set) != num_episodes`.

---

### 11. Scoring includes failed and cancelled episodes

**Severity:** Serious

**Where:** `bench_common/eval/metrics.py` — `compute_metric()`

**Problem:** All episodes regardless of status were included in metric aggregation. A failed episode (crash, timeout, etc.) has a `total_reward` of 0.0 which is indistinguishable from a legitimate zero score. This pulled leaderboard scores down artificially.

**Fix:** Added `_SCOREABLE_STATUSES = frozenset({"completed", "timeout"})` and filtered episodes before computing values. Failed and cancelled episodes are now excluded.

---

### 12. Sandbox port counter increments forever

**Severity:** Serious

**Where:** `bench-sandbox/app/manager.py`

**Problem:** Port assignment used a monotonically increasing counter. After enough `clone_and_start` / `stop_env` cycles, the counter would eventually exhaust all available ports. Stopped environments did not return their port to the pool.

**Fix:** Replaced the counter with a recycling set pool (`_available_ports`). Ports are allocated with `min()` on startup and returned with `.add()` in `stop_env()`.

---

### 13. `_github_url_for_domain` performed a full table scan

**Severity:** Moderate

**Where:** `bench_common/orchestrator/service.py` — `_github_url_for_domain()`

**Problem:** The query fetched all developer environments across all domains, then picked the first result. For platforms with many environments this was a progressively slower full scan.

**Fix:** Changed to `db.list_developer_environments(domain_id=domain_id)` to filter at query time.

---

### 14. Guest rate limit counted all-time runs instead of runs today

**Severity:** Moderate

**Where:** `bench-api/app/auth/policy.py` — `assert_guest_rate_limit()`

**Problem:** The daily run limit was enforced by counting a guest's total historical runs with no date filter. A guest who ran 5 episodes on day 1 would be blocked for all future days.

**Fix:** Added a `data__created_at__gte` filter on the ISO midnight prefix for the current UTC day. ISO-8601 strings are lexicographically ordered identically to chronological order, so `__gte` on a truncated midnight prefix is correct and index-friendly on Postgres `jsonb`.

---

## Changes Made

### Fix 5: Wrap agent loop in `try/finally` for guaranteed `env_client.close()`

**File:** `bench_common/runtime/agent_loop.py`

The entire `while True:` episode loop is now enclosed in a `try/finally`. The `finally` block calls `env_client.close()` in its own `try/except` so a failed close emits a warning but does not mask the original error.

---

### Fix 6: Detect all-failed runs before scoring

**File:** `bench_common/orchestrator/service.py`

In `_run_all_episodes()`, after gathering episode results, added:
```python
if all_eps and all(ep.status == "failed" for ep in all_eps):
    run.status = "failed"
    ...
    return
```
The run is marked `"failed"` and `compute_scores` is never called.

---

### Fix 7: Handle `asyncio.CancelledError` in `run_test_episode()`

**File:** `bench_common/orchestrator/service.py`

Added an explicit `except asyncio.CancelledError` block that sets `episode.status = "cancelled"`, `run.status = "cancelled"`, persists both, then re-raises.

---

### Fix 8: Add `require_worker` auth to claim endpoint

**File:** `bench-api/app/routes/bench.py`

Added `dependencies=[Depends(require_worker)]` to the `PATCH /jobs/{job_id}/claim` route decorator.

---

### Fix 9: Anchor binding vow version regexes

**File:** `bench_common/core/binding_vow.py`

Both compiled regexes now end with `$`:
- `_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")`
- `_VERSION_REQ_RE = re.compile(r"^[\^~]?\d+\.\d+(\.\d+)?$")`

---

### Fix 10: Validate `seed_set` length in `RunConfig`

**File:** `bench_common/core/run.py`

Added `@model_validator(mode="after")` to `RunConfig`:
```python
if self.seed_set is not None and len(self.seed_set) != self.num_episodes:
    raise ValueError("seed_set length must equal num_episodes")
```

---

### Fix 11: Exclude failed/cancelled episodes from scoring

**File:** `bench_common/eval/metrics.py`

Added `_SCOREABLE_STATUSES = frozenset({"completed", "timeout"})`. `compute_metric()` now filters to `scoreable = [ep for ep in episodes if ep.status in _SCOREABLE_STATUSES]` before building the values list.

---

### Fix 12: Recycling port pool in sandbox manager

**File:** `bench-sandbox/app/manager.py`

Replaced the incrementing counter with:
```python
_available_ports: set[int] = set(range(_PORT_RANGE_START, _PORT_RANGE_END + 1))
```
Ports are allocated with `min(_available_ports); _available_ports.discard(port)` and returned to the pool in `stop_env()` with `_available_ports.add(port)`.

---

### Fix 13: Filter developer environments by domain in query

**File:** `bench_common/orchestrator/service.py`

`_github_url_for_domain()` now passes `domain_id=domain_id` to `db.list_developer_environments()`.

---

### Fix 14: Scope guest rate limit to current UTC day

**File:** `bench-api/app/auth/policy.py`

```python
today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
count = await RunRow.objects.filter(
    actor_type=ActorType.GUEST,
    actor_id=guest_session_id,
    data__created_at__gte=today_iso,
).acount()
```

---

## Feature: Provider-native Structured Outputs

### Summary

The platform now enforces model response format natively for all three supported providers (OpenAI, Anthropic, Gemini) when the action space is typed. Environment developers no longer need to parse free-text model responses for structured actions.

### How it works

When `action_space.type` is `discrete`, `continuous`, `json`, or `composite`:

| Provider | Mechanism |
|----------|-----------|
| OpenAI (GPT-4o, o3, …) | `response_format: {"type": "json_schema", ...}` |
| Anthropic (Claude 3/4) | Forced `submit_action` tool call |
| Google (Gemini 1.5/2.x) | `response_format` via LiteLLM translation |

Text, image, and multi-modal action spaces fall back to the existing free-text parse path.

All three providers wrap the action value under a top-level `{"action": ...}` key in the schema, and the router unwraps it before calling `parse_action()`.

### New `parse_action()` hook on `BaseEnv`

**File:** `bench_common/env_sdk/base.py`

```python
def parse_action(self, action: Any) -> Any:
    """Identity by default. Override to remap the structured value before step()."""
    return action
```

The adapter server calls `env.parse_action(req.action)` before every `env.step(action)`.

Override only when the schema value and what `step()` expects are different types:
```python
def parse_action(self, action):
    return {"left": 0, "right": 1, "up": 2, "down": 3}[action]
```

### Files changed

| File | Change |
|------|--------|
| `bench_common/runtime/inference.py` | New module-level helpers (`_provider_key`, `_space_to_json_schema`, `_wrap_action_schema`); `decide()` dispatches to structured or free-text path; new `_supports_structured_output()` and `_extract_structured_action()` methods; `_build_messages()` / `_build_system_prompt()` accept `use_structured` and `provider` kwargs and vary the closing instruction accordingly |
| `bench_common/env_sdk/base.py` | Added `parse_action()` identity method with docstring |
| `bench_common/env_sdk/server.py` | `/step` handler calls `env.parse_action(req.action)` before `env.step(action)` |
| `services/bench/template/env.py` | Module docstring documents `parse_action` with examples |
| `bench_common/cli/templates/env.py` | Same; adds a commented-out `parse_action` stub |
