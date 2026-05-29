"""RunConfig enforces the platform max-episodes cap from settings."""

from __future__ import annotations

import pytest
from bench_common.config import settings
from bench_common.core.run import AgentConfig, RunConfig
from pydantic import ValidationError


def _base_config(**overrides):
    data = {
        "domain_id": "d1",
        "binding_vow_version": "1.0.0",
        "agent_config": AgentConfig(model="openai/gpt-4o"),
        "num_episodes": 1,
    }
    data.update(overrides)
    return RunConfig(**data)


def test_run_config_accepts_episodes_at_platform_cap(monkeypatch):
    monkeypatch.setattr(settings, "max_episodes_per_run", 20)
    config = _base_config(num_episodes=20)
    assert config.num_episodes == 20


def test_run_config_rejects_episodes_above_platform_cap(monkeypatch):
    monkeypatch.setattr(settings, "max_episodes_per_run", 20)
    with pytest.raises(ValidationError, match="exceeds the platform maximum \\(20\\)"):
        _base_config(num_episodes=21)


def test_run_config_rejects_zero_episodes():
    with pytest.raises(ValidationError):
        _base_config(num_episodes=0)
