"""RunConfig must expose env_id for orchestrator.create_run."""

from bench_common.core.run import AgentConfig, RunConfig


def test_run_config_env_id_defaults_to_none():
    config = RunConfig(
        domain_id="d1",
        binding_vow_version="1.0.0",
        agent_config=AgentConfig(model="openai/gpt-4o"),
        num_episodes=1,
    )
    assert config.env_id is None


def test_run_config_env_id_round_trip():
    config = RunConfig(
        domain_id="d1",
        binding_vow_version="1.0.0",
        agent_config=AgentConfig(model="openai/gpt-4o"),
        num_episodes=1,
        env_id="env-abc",
    )
    assert config.env_id == "env-abc"
