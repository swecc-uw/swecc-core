# Benchmark Orchestrator Platform — MVP Design Document

**Version:** 0.1.0-draft
**Date:** April 2026
**Status:** RFC

---

## 1. Executive Summary

This document specifies the MVP for a **distributed evaluation protocol** that sits between environment hosts, agent inference backends, and evaluation/leaderboard infrastructure. The core architectural bet: **clients own the environment runtime; the platform owns agent execution, API mediation, logging, scoring, and reproducibility.**

The platform models RL environments as **Domains**, formalizes their interaction contracts as **Binding Vows**, and provides modular **Techniques** (tool-calling, memory, multi-agent orchestration) that agents can compose at runtime.

The MVP targets Tier 1 (static datasets, text-interactive environments, browser/tool-use agents, multi-step API tasks) and Tier 2 (multimodal environments, multi-agent, partially observable, human-in-the-loop judging).

---

## 2. Terminology

| Term | Definition |
|---|---|
| **Domain** | A registered RL environment — its metadata, configuration, sandbox image, and runtime. |
| **Binding Vow** | A typed contract that formally specifies the observation space, action space, reward structure, episode semantics, and supported techniques for a Domain. It is the single source of truth for what an agent can send and receive. |
| **Technique** | A composable module (tool-calling harness, memory manager, multi-agent router, etc.) that an agent runtime can activate. A Domain's Binding Vow declares which Techniques it supports. |
| **Episode** | A single run of an agent inside a Domain from `reset()` to terminal state (or timeout). |
| **Run** | A batch of Episodes sharing the same agent config, Domain version, and seed set. A Run is the unit of leaderboard submission. |
| **Trace** | The complete log of an Episode — observations, actions, rewards, latencies, model calls, tool invocations, and internal agent state snapshots. |

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Platform Boundary                            │
│                                                                      │
│  ┌────────────┐   ┌──────────────────┐   ┌───────────────────────┐  │
│  │  API       │   │   Orchestrator   │   │   Agent Runtime       │  │
│  │  Gateway   │──▶│   (Job Queue +   │──▶│   (Sandboxed          │  │
│  │  (FastAPI) │   │    Scheduler)    │   │    Containers)        │  │
│  └─────┬──────┘   └────────┬─────────┘   └──────────┬────────────┘  │
│        │                   │                         │               │
│        │            ┌──────┴──────┐           ┌──────┴──────┐       │
│        │            │  Trace      │           │  Inference   │       │
│        │            │  Store      │           │  Router      │       │
│        │            │  (PG + S3)  │           │  (LiteLLM)   │       │
│        │            └─────────────┘           └──────────────┘       │
│        │                                                             │
│  ┌─────┴──────────────────────────────────────────────────────────┐  │
│  │                    Eval + Leaderboard Service                  │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
         ▲                                            │
         │          Environment Interface             │
         │          (gRPC / HTTP)                      ▼
┌────────────────────────────────────────────────────────────────┐
│                   Client Environment Host                      │
│  (remote server, sandbox image, or platform-hosted container)  │
└────────────────────────────────────────────────────────────────┘
```

### 3.1 Two Operating Modes

**Development Mode ("test via API"):** The client runs their environment on their own infrastructure. The platform's agent runtime connects to it over the network via the standard environment interface. Results are ephemeral — useful for iteration and debugging.

**Production Mode ("uploaded environment"):** The client packages their environment as a container image (OCI). The platform runs it in an isolated sandbox, connects the agent runtime to it locally, and records official Runs against the leaderboard.

---

## 4. Core Data Model

### 4.1 Binding Vow Schema

The Binding Vow is a versioned, machine-readable contract. It is the foundational abstraction.

```python
# src/core/binding_vow.py

from __future__ import annotations
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class SpaceType(str, Enum):
    DISCRETE = "discrete"
    CONTINUOUS = "continuous"
    TEXT = "text"
    JSON = "json"
    IMAGE = "image"
    MULTI_MODAL = "multi_modal"
    COMPOSITE = "composite"


class SpaceSpec(BaseModel):
    """Describes one leaf of an observation or action space."""
    type: SpaceType
    dtype: str | None = None                  # e.g. "float32", "uint8"
    shape: list[int] | None = None            # tensor dims, null for text/json
    bounds: dict[str, float] | None = None    # {"low": 0.0, "high": 1.0}
    enum_values: list[str] | None = None      # for discrete named actions
    schema_ref: str | None = None             # JSON Schema $ref for json type
    description: str = ""


class CompositeSpace(BaseModel):
    """A named dict of SpaceSpecs, for structured obs/action."""
    fields: dict[str, SpaceSpec | CompositeSpace]


class RewardSpec(BaseModel):
    type: Literal["scalar", "vector", "sparse", "binary"]
    range: dict[str, float] | None = None
    description: str = ""


class EpisodeSemantics(BaseModel):
    max_steps: int | None = None
    max_wall_seconds: int | None = None
    deterministic_reset: bool = False
    supports_seed: bool = True
    parallel_episodes: int = 1
    observability: Literal["full", "partial"] = "full"


class TechniqueDeclaration(BaseModel):
    """Declares that this Domain supports a given Technique."""
    technique_id: str                          # e.g. "tool_calling", "memory", "multi_agent"
    version: str = "^1.0"
    config_schema: dict[str, Any] | None = None  # JSON Schema for technique-specific params
    required: bool = False                     # must the agent use this?


class BindingVow(BaseModel):
    """
    The typed contract between a Domain and an Agent.
    Immutable once a Run references it — new versions get new IDs.
    """
    id: str = Field(..., description="Unique vow identifier, e.g. 'webarena-v2'")
    version: str = Field(..., description="SemVer string")
    domain_id: str
    tier: Literal["tier1", "tier2"]

    observation_space: SpaceSpec | CompositeSpace
    action_space: SpaceSpec | CompositeSpace
    reward: RewardSpec

    episode: EpisodeSemantics
    techniques: list[TechniqueDeclaration] = []

    metadata: dict[str, Any] = {}
    description: str = ""
```

### 4.2 Domain

```python
# src/core/domain.py

from pydantic import BaseModel, Field
from typing import Literal


class EnvironmentEndpoint(BaseModel):
    """How the platform reaches the environment."""
    mode: Literal["remote", "sandbox"]
    url: str | None = None            # remote mode: client's gRPC/HTTP URL
    image: str | None = None          # sandbox mode: OCI image ref
    resources: ResourceSpec | None = None


class ResourceSpec(BaseModel):
    cpu: str = "2"
    memory: str = "4Gi"
    gpu: str | None = None
    timeout_seconds: int = 3600


class Domain(BaseModel):
    id: str
    name: str
    owner_id: str                     # org or user
    binding_vow: BindingVow
    endpoint: EnvironmentEndpoint
    scoring: ScoringConfig
    status: Literal["draft", "testing", "published", "archived"] = "draft"
    tags: list[str] = []
```

### 4.3 Run, Episode, Trace

```python
# src/core/run.py

from pydantic import BaseModel
from datetime import datetime
from typing import Any


class RunConfig(BaseModel):
    domain_id: str
    binding_vow_version: str
    agent_config: AgentConfig
    seed_set: list[int] | None = None
    num_episodes: int = 1
    max_parallel: int = 1


class AgentConfig(BaseModel):
    model: str                         # LiteLLM model string
    system_prompt: str | None = None
    techniques: list[TechniqueConfig] = []
    temperature: float = 0.0
    max_tokens: int = 4096


class TechniqueConfig(BaseModel):
    technique_id: str
    params: dict[str, Any] = {}


class Episode(BaseModel):
    id: str
    run_id: str
    seed: int | None
    status: str                        # pending | running | completed | failed | timeout
    started_at: datetime | None
    ended_at: datetime | None
    steps: int = 0
    total_reward: float = 0.0
    terminal_info: dict[str, Any] = {}


class TraceEvent(BaseModel):
    episode_id: str
    step: int
    timestamp: datetime
    event_type: str                    # observation | action | reward | model_call | tool_call | technique_event
    payload: dict[str, Any]
```

---

## 5. Environment Interface Protocol

Environments expose a minimal, Gym-like interface over gRPC (primary) or HTTP/JSON (fallback for Tier 1 text-only environments).

### 5.1 Protobuf Definition

```protobuf
syntax = "proto3";
package orchestrator.env.v1;

service Environment {
    rpc Reset(ResetRequest)   returns (Observation);
    rpc Step(Action)          returns (StepResult);
    rpc Close(CloseRequest)   returns (CloseResponse);
    rpc Render(RenderRequest) returns (RenderResponse);  // optional
    rpc Seed(SeedRequest)     returns (SeedResponse);    // optional
}

message ResetRequest {
    string episode_id = 1;
    optional int64 seed = 2;
    map<string, string> scenario_params = 3;
}

message Observation {
    bytes data = 1;           // serialized per binding vow's observation_space
    string content_type = 2;  // "application/json", "image/png", etc.
}

message Action {
    string episode_id = 1;
    bytes data = 2;           // serialized per binding vow's action_space
    string content_type = 3;
}

message StepResult {
    Observation observation = 1;
    double reward = 2;
    bool terminated = 3;
    bool truncated = 4;
    map<string, string> info = 5;
}

message RenderRequest {
    string episode_id = 1;
    string mode = 2;  // "text", "rgb_array", "html"
}

message RenderResponse {
    bytes data = 1;
    string content_type = 2;
}

message ResetRequest { /* ... */ }
message CloseRequest { string episode_id = 1; }
message CloseResponse {}
message SeedRequest { int64 seed = 1; }
message SeedResponse {}
```

### 5.2 HTTP Fallback (Tier 1 Text Environments)

For simple text-only environments, clients can implement a REST adapter instead of gRPC:

```
POST /reset          { "episode_id": "...", "seed": 42 }  → Observation JSON
POST /step           { "episode_id": "...", "action": {...} }  → StepResult JSON
POST /close          { "episode_id": "..." }  → {}
GET  /health         → { "status": "ok" }
```

---

## 6. Techniques System

Techniques are modular capabilities that augment agent behavior. They are first-class platform objects with their own interface contract.

### 6.1 Technique Interface

```python
# src/techniques/base.py

from abc import ABC, abstractmethod
from typing import Any
from src.core.binding_vow import TechniqueDeclaration


class Technique(ABC):
    """Base interface all Techniques implement."""

    @abstractmethod
    def id(self) -> str: ...

    @abstractmethod
    def compatible(self, declaration: TechniqueDeclaration) -> bool:
        """Check if this implementation satisfies the domain's declaration."""
        ...

    @abstractmethod
    async def on_episode_start(self, episode_id: str, config: dict[str, Any]) -> None: ...

    @abstractmethod
    async def before_action(
        self,
        observation: Any,
        agent_state: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Inject context into the agent's decision.
        Returns additional context to merge into the model prompt.
        """
        ...

    @abstractmethod
    async def after_action(
        self,
        action: Any,
        step_result: Any,
        agent_state: dict[str, Any],
    ) -> None:
        """Post-step bookkeeping (memory writes, coordination, etc.)."""
        ...

    @abstractmethod
    async def on_episode_end(self, episode_id: str, terminal_info: dict[str, Any]) -> None: ...
```

### 6.2 Built-in Techniques (MVP)

```python
# src/techniques/tool_calling.py

class ToolCallingTechnique(Technique):
    """
    Provides structured tool/function calling.
    The Binding Vow's technique config defines available tools as JSON Schema.
    At runtime, tools are injected into the LLM prompt as function definitions
    and tool calls are parsed, dispatched, and results fed back before the
    agent selects an environment action.
    """
    def id(self) -> str:
        return "tool_calling"


# src/techniques/memory.py

class EpisodicMemoryTechnique(Technique):
    """
    Short-term memory within an episode (sliding window + summarization).
    Long-term memory across episodes within a Run (vector store).
    """
    def id(self) -> str:
        return "memory"


# src/techniques/multi_agent.py

class MultiAgentTechnique(Technique):
    """
    Manages multiple named agent roles within a single episode.
    The Binding Vow specifies roles, turn order, and communication channels.
    Each role can use a different model or prompt.
    """
    def id(self) -> str:
        return "multi_agent"
```

---

## 7. Agent Runtime

The agent runtime is the inner loop. It runs inside an isolated container per Episode, receives observations, invokes Techniques, calls models via LiteLLM, and emits actions.

```python
# src/runtime/agent_loop.py

from src.core.binding_vow import BindingVow
from src.techniques.base import Technique
from src.runtime.inference import InferenceRouter


class AgentLoop:
    def __init__(
        self,
        binding_vow: BindingVow,
        agent_config: AgentConfig,
        techniques: list[Technique],
        inference: InferenceRouter,
        trace_sink: TraceSink,
    ):
        self.vow = binding_vow
        self.config = agent_config
        self.techniques = techniques
        self.inference = inference
        self.trace = trace_sink
        self.state: dict = {}

    async def run_episode(self, env_client, episode_id: str, seed: int | None) -> Episode:
        obs = await env_client.reset(episode_id=episode_id, seed=seed)
        self.trace.record("observation", step=0, payload=obs)

        for technique in self.techniques:
            await technique.on_episode_start(episode_id, self.config.techniques_for(technique.id()))

        step = 0
        total_reward = 0.0

        while True:
            step += 1

            # --- Pre-action technique pass ---
            augmented_context = {}
            for technique in self.techniques:
                ctx = await technique.before_action(obs, self.state)
                augmented_context.update(ctx)

            # --- Model inference ---
            action = await self.inference.decide(
                observation=obs,
                binding_vow=self.vow,
                agent_config=self.config,
                extra_context=augmented_context,
                step=step,
            )
            self.trace.record("action", step=step, payload=action)

            # --- Environment step ---
            result = await env_client.step(episode_id=episode_id, action=action)
            self.trace.record("step_result", step=step, payload=result)
            total_reward += result.reward

            # --- Post-action technique pass ---
            for technique in self.techniques:
                await technique.after_action(action, result, self.state)

            if result.terminated or result.truncated:
                break
            if self.vow.episode.max_steps and step >= self.vow.episode.max_steps:
                break

            obs = result.observation

        for technique in self.techniques:
            await technique.on_episode_end(episode_id, result.info)

        return Episode(
            id=episode_id,
            steps=step,
            total_reward=total_reward,
            terminal_info=result.info,
        )
```

### 7.1 Inference Router (LiteLLM)

```python
# src/runtime/inference.py

import litellm


class InferenceRouter:
    """
    Wraps LiteLLM to provide model-agnostic inference.
    Handles prompt construction from observation + binding vow + technique context.
    """

    async def decide(
        self,
        observation,
        binding_vow: BindingVow,
        agent_config: AgentConfig,
        extra_context: dict,
        step: int,
    ) -> dict:
        messages = self._build_messages(observation, binding_vow, agent_config, extra_context, step)

        response = await litellm.acompletion(
            model=agent_config.model,
            messages=messages,
            temperature=agent_config.temperature,
            max_tokens=agent_config.max_tokens,
        )

        return self._parse_action(response, binding_vow.action_space)

    def _build_messages(self, observation, vow, config, extra_context, step) -> list[dict]:
        system = self._build_system_prompt(vow, config, extra_context)
        user = self._serialize_observation(observation, vow.observation_space, step)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _build_system_prompt(self, vow, config, extra_context) -> str:
        parts = []
        if config.system_prompt:
            parts.append(config.system_prompt)

        parts.append(f"## Domain Contract\n{vow.description}")
        parts.append(f"## Action Space\n{self._describe_space(vow.action_space)}")

        if extra_context:
            for key, value in extra_context.items():
                parts.append(f"## {key}\n{value}")

        return "\n\n".join(parts)
```

---

## 8. Orchestrator Service

The Orchestrator is the control plane. It accepts Run requests, schedules Episodes, manages sandboxes, and coordinates evaluation.

```python
# src/orchestrator/service.py

from src.core.run import RunConfig, Run, Episode
from src.orchestrator.scheduler import Scheduler
from src.orchestrator.sandbox import SandboxManager


class OrchestratorService:
    def __init__(self, scheduler: Scheduler, sandbox_mgr: SandboxManager, db, trace_store):
        self.scheduler = scheduler
        self.sandbox_mgr = sandbox_mgr
        self.db = db
        self.trace_store = trace_store

    async def create_run(self, config: RunConfig, requester_id: str) -> Run:
        # 1. Validate binding vow compatibility
        domain = await self.db.get_domain(config.domain_id)
        vow = domain.binding_vow
        assert vow.version == config.binding_vow_version

        # 2. Validate technique compatibility
        for tc in config.agent_config.techniques:
            decl = next((t for t in vow.techniques if t.technique_id == tc.technique_id), None)
            if decl is None:
                raise ValueError(f"Technique '{tc.technique_id}' not declared in binding vow")

        # 3. Create Run record
        run = Run(config=config, requester_id=requester_id, status="pending")
        await self.db.save_run(run)

        # 4. Schedule episodes
        seeds = config.seed_set or list(range(config.num_episodes))
        for seed in seeds:
            episode = Episode(run_id=run.id, seed=seed, status="pending")
            await self.scheduler.enqueue(episode, domain, config.agent_config)

        return run

    async def on_episode_complete(self, episode: Episode):
        run = await self.db.get_run(episode.run_id)
        episodes = await self.db.get_episodes(run.id)

        if all(e.status in ("completed", "failed", "timeout") for e in episodes):
            await self._finalize_run(run, episodes)

    async def _finalize_run(self, run, episodes):
        domain = await self.db.get_domain(run.config.domain_id)
        scores = await self.eval_service.compute(domain.scoring, episodes)
        await self.leaderboard.submit(domain.id, run, scores)
        run.status = "completed"
        await self.db.save_run(run)
```

---

## 9. Scoring and Leaderboard

### 9.1 Scoring Config

```python
# src/core/scoring.py

from pydantic import BaseModel
from typing import Literal, Any


class MetricDef(BaseModel):
    name: str                          # e.g. "success_rate", "avg_reward", "steps_to_goal"
    type: Literal["episode_reward", "terminal_field", "trajectory_judge", "human_judge"]
    aggregation: Literal["mean", "median", "max", "min", "sum", "pass_rate"]
    field: str | None = None           # for terminal_field: key in episode.terminal_info
    judge_config: dict[str, Any] | None = None  # for *_judge types


class ScoringConfig(BaseModel):
    primary_metric: str                # name of the main ranking metric
    metrics: list[MetricDef]
    higher_is_better: bool = True
```

### 9.2 Leaderboard Schema (Postgres)

```sql
CREATE TABLE leaderboard_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id       TEXT NOT NULL REFERENCES domains(id),
    run_id          UUID NOT NULL REFERENCES runs(id),
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitter_id    TEXT NOT NULL,
    model           TEXT NOT NULL,
    agent_config    JSONB NOT NULL,
    binding_vow_ver TEXT NOT NULL,

    -- Denormalized scores for fast queries
    primary_score   DOUBLE PRECISION NOT NULL,
    all_scores      JSONB NOT NULL,        -- { "success_rate": 0.85, "avg_steps": 12.3, ... }

    -- Reproducibility
    seed_set        INTEGER[] NOT NULL,
    num_episodes    INTEGER NOT NULL,
    trace_ref       TEXT NOT NULL,          -- S3 prefix for trace bundle

    UNIQUE (domain_id, run_id)
);

CREATE INDEX idx_leaderboard_domain_score
    ON leaderboard_entries (domain_id, primary_score DESC);
```

### 9.3 Human-in-the-Loop Judging (Tier 2)

For domains requiring human evaluation, the platform provides a judging queue:

```python
# src/eval/human_judge.py

class HumanJudgeService:
    """
    Pushes completed episode traces into a review queue.
    Judges access a web UI that replays episodes and collects ratings.
    Scores are aggregated once quorum is met.
    """

    async def enqueue_for_review(self, episode_id: str, judge_config: dict):
        # Create judging task with replay link and rubric
        ...

    async def submit_judgment(self, episode_id: str, judge_id: str, scores: dict):
        # Store judgment; check if quorum reached
        ...

    async def aggregate(self, episode_id: str) -> dict[str, float]:
        # Cohen's kappa for agreement, then average scores
        ...
```

---

## 10. API Surface

### 10.1 REST API (FastAPI)

```
# --- Domains ---
POST   /v1/domains                     Create a Domain (draft)
GET    /v1/domains/{id}                Get Domain + Binding Vow
PATCH  /v1/domains/{id}                Update Domain (draft only)
POST   /v1/domains/{id}/publish        Publish (freeze vow, enable leaderboard)
POST   /v1/domains/{id}/upload-image   Upload sandbox OCI image

# --- Testing (Development Mode) ---
POST   /v1/test/episode                Run a single test episode against a remote env
GET    /v1/test/episode/{id}           Poll episode status + get trace
GET    /v1/test/episode/{id}/replay    Stream replay events

# --- Runs (Production Mode) ---
POST   /v1/runs                        Create a Run (batch of episodes)
GET    /v1/runs/{id}                   Run status + episode summaries
GET    /v1/runs/{id}/episodes          List episodes with scores
GET    /v1/runs/{id}/traces            Download trace bundle

# --- Leaderboard ---
GET    /v1/leaderboards/{domain_id}                   Get rankings
GET    /v1/leaderboards/{domain_id}/compare            Compare two entries
GET    /v1/leaderboards/{domain_id}/history/{model}    Score history for a model

# --- Techniques ---
GET    /v1/techniques                  List available techniques
GET    /v1/techniques/{id}             Technique schema + docs

# --- Admin ---
GET    /v1/usage                       Quota and billing summary
```

### 10.2 WebSocket (Trace Streaming)

```
WS /v1/ws/episodes/{id}/trace

→ server pushes TraceEvent JSON frames in real-time as the episode runs
→ client can send { "command": "pause" | "resume" | "cancel" }
```

---

## 11. Sandbox Architecture

When an environment is "uploaded," the platform runs it in an isolated sandbox.

```
┌─────────────────────── Pod ───────────────────────┐
│                                                    │
│  ┌──────────────┐       ┌──────────────────────┐  │
│  │  Env Container│◄─────▶│  Agent Container     │  │
│  │  (client OCI) │ gRPC  │  (platform runtime)  │  │
│  │               │ over  │                      │  │
│  │  - reset()    │ lo    │  - AgentLoop         │  │
│  │  - step()     │       │  - Techniques        │  │
│  │  - render()   │       │  - InferenceRouter   │  │
│  └──────────────┘       └──────────────────────┘  │
│                                                    │
│  Network policy: env container has NO egress.      │
│  Agent container: egress only to LiteLLM proxy.    │
└────────────────────────────────────────────────────┘
```

Key security constraints:
- Environment container: no network egress, capped CPU/memory/GPU per `ResourceSpec`
- Agent container: egress restricted to the platform's LiteLLM proxy endpoint
- Ephemeral filesystem; no persistent volumes
- Episode timeout enforced by the orchestrator (kills pod on expiry)

---

## 12. Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| **Language** | Python 3.12+ | Ecosystem fit (ML, LiteLLM, FastAPI) |
| **Package Manager** | `uv` | Fast, lockfile-based, reproducible |
| **API Framework** | FastAPI + Uvicorn | Async, OpenAPI, WebSocket support |
| **Task Queue** | Celery + Redis | Proven job scheduling; swap for Temporal later |
| **Database** | PostgreSQL 16 | Leaderboard, domains, runs, episodes |
| **Trace Storage** | S3-compatible (MinIO local) | Append-heavy, immutable blobs |
| **Inference Proxy** | LiteLLM | Unified interface across model providers |
| **Env Protocol** | gRPC (grpcio) + HTTP fallback | Streaming, typed, performant |
| **Container Orchestration** | Docker (dev), K8s (prod) | Sandbox isolation |
| **Migrations** | Alembic | Schema versioning |
| **Testing** | pytest + pytest-asyncio | Standard |
| **CI** | GitHub Actions | Standard |

---

## 13. Project Structure

```
benchmark-orchestrator/
├── pyproject.toml                  # uv project config
├── uv.lock
├── README.md
├── alembic/                        # DB migrations
│   └── versions/
├── proto/
│   └── orchestrator/env/v1/
│       └── environment.proto
├── src/
│   ├── __init__.py
│   ├── core/                       # Domain models
│   │   ├── binding_vow.py
│   │   ├── domain.py
│   │   ├── run.py
│   │   ├── scoring.py
│   │   └── technique_registry.py
│   ├── api/                        # FastAPI routes
│   │   ├── app.py
│   │   ├── routes/
│   │   │   ├── domains.py
│   │   │   ├── runs.py
│   │   │   ├── test.py
│   │   │   ├── leaderboard.py
│   │   │   └── techniques.py
│   │   └── ws/
│   │       └── trace_stream.py
│   ├── orchestrator/               # Scheduling + coordination
│   │   ├── service.py
│   │   ├── scheduler.py
│   │   └── sandbox.py
│   ├── runtime/                    # Agent execution
│   │   ├── agent_loop.py
│   │   ├── inference.py
│   │   └── env_client.py
│   ├── techniques/                 # Technique implementations
│   │   ├── base.py
│   │   ├── tool_calling.py
│   │   ├── memory.py
│   │   └── multi_agent.py
│   ├── eval/                       # Scoring + judging
│   │   ├── evaluator.py
│   │   ├── metrics.py
│   │   └── human_judge.py
│   ├── storage/                    # DB + object store
│   │   ├── database.py
│   │   ├── trace_store.py
│   │   └── models.py              # SQLAlchemy models
│   └── config.py                   # Settings via pydantic-settings
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│       └── sample_vows/            # Example binding vow JSONs
├── docker/
│   ├── Dockerfile.api
│   ├── Dockerfile.agent-runtime
│   └── docker-compose.yml
└── scripts/
    ├── seed_db.py
    └── run_local_episode.py
```

---

## 14. Binding Vow Examples

### 14.1 Tier 1 — Static NLP Benchmark

```json
{
  "id": "mmlu-pro",
  "version": "1.0.0",
  "domain_id": "mmlu-pro",
  "tier": "tier1",
  "observation_space": {
    "type": "json",
    "schema_ref": "#/definitions/MMLUQuestion",
    "description": "Multiple choice question with subject metadata"
  },
  "action_space": {
    "type": "discrete",
    "enum_values": ["A", "B", "C", "D"],
    "description": "Selected answer"
  },
  "reward": {
    "type": "binary",
    "range": {"low": 0, "high": 1},
    "description": "1 if correct, 0 otherwise"
  },
  "episode": {
    "max_steps": 1,
    "deterministic_reset": true,
    "supports_seed": true
  },
  "techniques": []
}
```

### 14.2 Tier 1 — Browser Agent (WebArena-style)

```json
{
  "id": "webarena-shopping",
  "version": "2.1.0",
  "domain_id": "webarena",
  "tier": "tier1",
  "observation_space": {
    "fields": {
      "screenshot": { "type": "image", "dtype": "uint8", "shape": [1024, 768, 3] },
      "accessibility_tree": { "type": "text" },
      "url": { "type": "text" }
    }
  },
  "action_space": {
    "type": "json",
    "schema_ref": "#/definitions/BrowserAction",
    "description": "click(x,y) | type(text) | scroll(dir) | goto(url) | done(answer)"
  },
  "reward": {
    "type": "sparse",
    "range": {"low": 0, "high": 1}
  },
  "episode": {
    "max_steps": 30,
    "max_wall_seconds": 300,
    "observability": "partial"
  },
  "techniques": [
    {
      "technique_id": "tool_calling",
      "version": "^1.0",
      "config_schema": {
        "tools": ["screenshot_annotator", "html_inspector"]
      }
    },
    {
      "technique_id": "memory",
      "version": "^1.0",
      "config_schema": {
        "window_size": 10,
        "summarize_after": 5
      }
    }
  ]
}
```

### 14.3 Tier 2 — Multi-Agent Negotiation

```json
{
  "id": "negotiation-arena-v1",
  "version": "1.0.0",
  "domain_id": "negotiation-arena",
  "tier": "tier2",
  "observation_space": {
    "fields": {
      "message_history": { "type": "json" },
      "private_valuation": { "type": "json" },
      "round": { "type": "discrete", "enum_values": [] }
    }
  },
  "action_space": {
    "type": "json",
    "schema_ref": "#/definitions/NegotiationAction",
    "description": "propose(offer) | accept | reject | message(text)"
  },
  "reward": {
    "type": "scalar",
    "range": {"low": -100, "high": 100}
  },
  "episode": {
    "max_steps": 50,
    "observability": "partial",
    "parallel_episodes": 1
  },
  "techniques": [
    {
      "technique_id": "multi_agent",
      "version": "^1.0",
      "required": true,
      "config_schema": {
        "roles": ["buyer", "seller"],
        "turn_order": "alternating",
        "communication": "shared_channel"
      }
    },
    {
      "technique_id": "memory",
      "version": "^1.0"
    }
  ]
}
```

---

## 15. Episode Lifecycle (Sequence)

```
Client/User              API Gateway         Orchestrator        Scheduler         Agent Runtime        Env (sandbox/remote)
    │                        │                    │                  │                   │                      │
    ├── POST /v1/runs ──────▶│                    │                  │                   │                      │
    │                        ├── validate ───────▶│                  │                   │                      │
    │                        │                    ├── create Run ────┤                   │                      │
    │                        │                    ├── enqueue eps ──▶│                   │                      │
    │                        │◀── 202 Run created─┤                  │                   │                      │
    │◀── run_id ─────────────┤                    │                  │                   │                      │
    │                        │                    │                  │                   │                      │
    │                        │                    │              ┌───┴───┐               │                      │
    │                        │                    │              │ dequeue│               │                      │
    │                        │                    │              │episode │               │                      │
    │                        │                    │              └───┬───┘               │                      │
    │                        │                    │                  ├── spawn pod ──────▶│                      │
    │                        │                    │                  │                   ├── reset() ───────────▶│
    │                        │                    │                  │                   │◀── observation ───────┤
    │                        │                    │                  │                   │                      │
    │                        │                    │                  │                   │── LiteLLM call ──┐   │
    │                        │                    │                  │                   │◀─ action ────────┘   │
    │                        │                    │                  │                   │                      │
    │                        │                    │                  │                   ├── step(action) ─────▶│
    │                        │                    │                  │                   │◀── step_result ──────┤
    │                        │                    │                  │                   │                      │
    │                        │                    │                  │                   │   ... loop ...        │
    │                        │                    │                  │                   │                      │
    │                        │                    │                  │                   ├── close() ──────────▶│
    │                        │                    │                  │◀── episode done ──┤                      │
    │                        │                    │◀── scores ───────┤                   │                      │
    │                        │                    ├── leaderboard ───┤                   │                      │
    │                        │                    │                  │                   │                      │
    ├── GET /v1/runs/{id} ──▶│                    │                  │                   │                      │
    │◀── completed + scores ─┤                    │                  │                   │                      │
```

---

## 16. Configuration

```python
# src/config.py

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database
    database_url: str = "postgresql+asyncpg://localhost:5432/orchestrator"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Object storage
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "traces"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"

    # LiteLLM
    litellm_proxy_url: str = "http://localhost:4000"

    # Sandbox
    sandbox_mode: str = "docker"  # "docker" | "k8s"
    agent_runtime_image: str = "orchestrator/agent-runtime:latest"
    default_env_timeout: int = 3600

    # Quotas
    max_parallel_episodes: int = 10
    max_episodes_per_run: int = 1000

    model_config = {"env_prefix": "ORCH_"}
```

---

## 17. pyproject.toml

```toml
[project]
name = "benchmark-orchestrator"
version = "0.1.0"
description = "Distributed evaluation protocol for AI agent benchmarks"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.9",
    "pydantic-settings>=2.5",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "celery[redis]>=5.4",
    "redis>=5.0",
    "litellm>=1.50",
    "grpcio>=1.68",
    "grpcio-tools>=1.68",
    "boto3>=1.35",
    "docker>=7.0",
    "websockets>=13.0",
    "httpx>=0.27",
    "structlog>=24.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "ruff>=0.8",
    "mypy>=1.13",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.mypy]
python_version = "3.12"
strict = true
```

---

## 18. MVP Scope and Milestones

### Phase 1 — Foundation (Weeks 1–3)
- Core data models (BindingVow, Domain, Run, Episode, Trace)
- PostgreSQL schema + Alembic migrations
- FastAPI skeleton with domain CRUD and run creation
- gRPC environment client + HTTP fallback
- Basic agent loop (no techniques) with LiteLLM inference
- Trace recording to S3
- Test endpoint: single episode against remote environment

### Phase 2 — Techniques + Scoring (Weeks 4–6)
- Technique interface + registry
- Tool-calling technique
- Episodic memory technique
- Scoring engine (episode_reward, terminal_field, trajectory_judge)
- Leaderboard service + API
- WebSocket trace streaming

### Phase 3 — Sandbox + Production Mode (Weeks 7–9)
- Docker sandbox manager (local)
- Image upload + validation pipeline
- Network isolation policies
- Run scheduler with parallelism control
- Replay viewer (API-driven; UI is out of scope for MVP)

### Phase 4 — Tier 2 + Hardening (Weeks 10–12)
- Multi-agent technique
- Partial observability support in agent loop
- Human-in-the-loop judging queue + API
- Quota enforcement + basic billing hooks
- Reproducibility: seed pinning, config snapshotting, trace diffing
- Integration tests with 2–3 reference domains

---

## 19. Open Questions
1. **Binding Vow versioning policy** — Should vow updates always create a new version (append-only), or allow in-place edits while a domain is in draft?

Answer: The preferred design is to develop a Binding Vow at the completion of the environment or benchmark. Thus this should create a new version.

2. **Trace format** — JSON-lines per episode vs. a structured format like OpenTelemetry spans? JSONL is simpler; OTel gives free tooling.

Answer: OpenTelemetry

3. **Multi-agent identity** — When multiple agents share an episode, does the leaderboard track the ensemble or individual role configs?

Answer: Leaderboards should track ensembles but allow for deeper data analysis for per player in an episode

4. **LiteLLM deployment** — Run as a sidecar per agent container, or as a shared proxy? Sidecar is simpler to isolate; shared proxy is cheaper.

Answer: Shared proxy

5. **Technique composition conflicts** — If two techniques both inject system prompt context, what's the merge order? Alphabetical by ID, or explicit priority in the vow?

Answer: Use a queuing system, but default to definitions in the vow if they exist
