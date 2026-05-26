"""Tests for run ↔ developer environment association helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from bench_common.core.run import AgentConfig, Run, RunConfig
from bench_common.core.run_env import merge_run_env_id, validate_env_domain_match


def test_validate_env_domain_match_ok():
    env = {"id": "env-1", "domain_id": "domain-a"}
    validate_env_domain_match(env, "env-1", "domain-a")


def test_validate_env_domain_match_missing_env():
    with pytest.raises(ValueError, match="not found"):
        validate_env_domain_match(None, "env-1", "domain-a")


def test_validate_env_domain_match_wrong_domain():
    env = {"id": "env-1", "domain_id": "other-domain"}
    with pytest.raises(ValueError, match="not 'domain-a'"):
        validate_env_domain_match(env, "env-1", "domain-a")


def test_merge_run_env_id_from_row():
    config = RunConfig(
        domain_id="d1",
        binding_vow_version="1",
        agent_config=AgentConfig(model="m"),
        num_episodes=1,
    )
    run = Run(config=config, requester_id="u1")
    row = SimpleNamespace(environment_id="env-abc")
    merged = merge_run_env_id(run, row.environment_id)
    assert merged.env_id == "env-abc"
