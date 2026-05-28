from __future__ import annotations

from typing import Any

import pytest
from bench_common.config import settings
from bench_common.core.binding_vow import BindingVow
from bench_common.core.run import AgentConfig, TraceEvent
from bench_common.runtime.agent_loop import AgentLoop
from bench_common.runtime.env_client import Observation, StepResult
from bench_common.runtime.inference import DecideResult


class FakeTraceStore:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    async def append(self, event: TraceEvent) -> None:
        self.events.append(event)


class NeverTerminatingEnv:
    def __init__(self) -> None:
        self.step_count = 0
        self.closed = False

    async def reset(self, episode_id: str, seed: int | None = None) -> Observation:
        return Observation(data={"episode_id": episode_id, "seed": seed})

    async def step(self, episode_id: str, action: Any) -> StepResult:
        self.step_count += 1
        return StepResult(
            observation=Observation(data={"step": self.step_count}),
            reward=0.0,
            terminated=False,
            truncated=False,
            info={},
        )

    async def close(self, episode_id: str) -> None:
        self.closed = True


class FakeInference:
    async def decide(self, **kwargs: Any) -> DecideResult:
        return DecideResult(action="noop", reasoning_text="reason")


def _vow(max_steps: int | None) -> BindingVow:
    return BindingVow(
        id="cap-test-vow",
        version="1.0.0",
        domain_id="cap-test",
        tier="tier1",
        observation_space={"type": "text", "description": "state"},
        action_space={"type": "text", "description": "action"},
        reward={"type": "scalar", "description": "reward"},
        episode={"max_steps": max_steps, "supports_seed": True},
        techniques=[],
    )


@pytest.mark.asyncio
async def test_episode_uses_platform_step_cap_when_vow_is_unbounded(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_episode_steps", 35)
    env = NeverTerminatingEnv()
    loop = AgentLoop(
        binding_vow=_vow(None),
        agent_config=AgentConfig(model="test-model"),
        techniques=[],
        inference=FakeInference(),
        trace=FakeTraceStore(),
    )

    episode = await loop.run_episode(env_client=env, episode_id="ep-1", seed=123)

    assert episode.status == "truncated"
    assert episode.steps == 35
    assert env.step_count == 35
    assert env.closed is True
    assert episode.terminal_info["reason"] == "step_limit"
    assert episode.terminal_info["platform_max_steps"] == 35


@pytest.mark.asyncio
async def test_episode_uses_lower_declared_step_cap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_episode_steps", 35)
    env = NeverTerminatingEnv()
    loop = AgentLoop(
        binding_vow=_vow(5),
        agent_config=AgentConfig(model="test-model"),
        techniques=[],
        inference=FakeInference(),
        trace=FakeTraceStore(),
    )

    episode = await loop.run_episode(env_client=env, episode_id="ep-2", seed=None)

    assert episode.status == "truncated"
    assert episode.steps == 5
    assert env.step_count == 5
    assert episode.terminal_info["max_steps"] == 5
    assert episode.terminal_info["declared_max_steps"] == 5


@pytest.mark.asyncio
async def test_episode_clamps_large_declared_step_cap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_episode_steps", 35)
    env = NeverTerminatingEnv()
    loop = AgentLoop(
        binding_vow=_vow(200),
        agent_config=AgentConfig(model="test-model"),
        techniques=[],
        inference=FakeInference(),
        trace=FakeTraceStore(),
    )

    episode = await loop.run_episode(env_client=env, episode_id="ep-3", seed=None)

    assert episode.status == "truncated"
    assert episode.steps == 35
    assert env.step_count == 35
    assert episode.terminal_info["declared_max_steps"] == 200
    assert episode.terminal_info["platform_max_steps"] == 35
