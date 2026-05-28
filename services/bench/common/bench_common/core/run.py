from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


def _new_id() -> str:
    return str(uuid.uuid4())


class TechniqueConfig(BaseModel):
    technique_id: str
    params: dict[str, Any] = {}


class AgentConfig(BaseModel):
    model: str
    system_prompt: str | None = None
    techniques: list[TechniqueConfig] = []
    temperature: float = 0.0
    max_tokens: int = 4096

    def techniques_for(self, technique_id: str) -> dict[str, Any]:
        for tc in self.techniques:
            if tc.technique_id == technique_id:
                return tc.params
        return {}


MAX_EPISODES_PER_RUN = 1000


class RunConfig(BaseModel):
    domain_id: str
    binding_vow_version: str
    agent_config: AgentConfig
    seed_set: list[int] | None = None
    # num_episodes constrained at the model level so a 0 or negative value can
    # never reach the orchestrator and produce a phantom 0.0 leaderboard entry.
    num_episodes: int = Field(default=1, ge=1, le=MAX_EPISODES_PER_RUN)
    max_parallel: int = Field(default=1, ge=1)
    env_id: str | None = None

    @model_validator(mode="after")
    def _seed_set_matches_num_episodes(self) -> "RunConfig":
        if self.seed_set is not None and len(self.seed_set) != self.num_episodes:
            raise ValueError(
                f"seed_set has {len(self.seed_set)} entries but num_episodes is "
                f"{self.num_episodes}; they must match, or omit seed_set to auto-generate seeds"
            )
        return self


class Run(BaseModel):
    id: str = Field(default_factory=_new_id)
    config: RunConfig
    requester_id: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    scores: dict[str, float] = {}
    team_id: str | None = None
    env_id: str | None = None


class Episode(BaseModel):
    id: str = Field(default_factory=_new_id)
    run_id: str
    seed: int | None = None
    status: Literal[
        "pending", "running", "completed", "truncated", "failed", "timeout", "cancelled"
    ] = "pending"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    steps: int = 0
    total_reward: float = 0.0
    terminal_info: dict[str, Any] = {}


class TraceEvent(BaseModel):
    episode_id: str
    step: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: Literal[
        "observation",
        "action",
        "reward",
        "model_call",
        "tool_call",
        "technique_event",
        "step_result",
        "episode_start",
        "episode_end",
    ]
    payload: dict[str, Any]
