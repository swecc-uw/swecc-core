from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


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


class RunConfig(BaseModel):
    domain_id: str
    binding_vow_version: str
    agent_config: AgentConfig
    seed_set: list[int] | None = None
    num_episodes: int = 1
    max_parallel: int = 1
    env_id: str | None = None


class Run(BaseModel):
    id: str = Field(default_factory=_new_id)
    config: RunConfig
    requester_id: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    scores: dict[str, float] = {}
    env_id: str | None = None


class Episode(BaseModel):
    id: str = Field(default_factory=_new_id)
    run_id: str
    seed: int | None = None
    status: Literal["pending", "running", "completed", "failed", "timeout"] = "pending"
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
