"""Ensure mesocosm run local does not require the Django bench app at import time."""

from __future__ import annotations

import argparse
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bench_common.cli import main as cli_main


def test_import_inference_bench_without_bench_models() -> None:
    for key in list(sys.modules):
        if key == "bench" or key.startswith("bench."):
            del sys.modules[key]
    if "bench_common.inference.bench" in sys.modules:
        del sys.modules["bench_common.inference.bench"]

    import bench_common.inference.bench as bench_mod  # noqa: WPS433

    assert "bench.models" not in sys.modules


@pytest.mark.asyncio
async def test_bench_with_domain_skips_database_import() -> None:
    from bench_common.core.binding_vow import BindingVow
    from bench_common.core.domain import EnvironmentEndpoint
    from bench_common.core.scoring import MetricDef, ScoringConfig
    from bench_common.env_sdk.registration import DomainConfig
    from bench_common.inference.bench import bench

    vow = BindingVow(
        id="t-v1",
        version="1.0.0",
        domain_id="t",
        tier="tier1",
        description="d",
        observation_space={"type": "text", "description": "o"},
        action_space={"type": "text", "description": "a"},
        reward={"type": "scalar", "description": "r"},
        episode={"max_steps": 1, "supports_seed": True, "deterministic_reset": True},
        techniques=[],
    )
    domain = DomainConfig(
        id="t",
        name="T",
        binding_vow=vow,
        endpoint=EnvironmentEndpoint(mode="remote", url="http://127.0.0.1:1"),
        scoring=ScoringConfig(
            primary_metric="accuracy",
            higher_is_better=True,
            metrics=[
                MetricDef(name="accuracy", type="episode_reward", aggregation="pass_rate"),
            ],
        ),
    )

    health = AsyncMock(return_value=False)
    env_client = MagicMock()
    env_client.health = health
    env_client.__aenter__ = AsyncMock(return_value=env_client)
    env_client.__aexit__ = AsyncMock(return_value=None)

    with patch("bench_common.inference.bench.HttpEnvClient", return_value=env_client):
        with pytest.raises(ConnectionError):
            await bench(
                model="ollama/llama3.2",
                domain_id="t",
                env_url="http://127.0.0.1:1",
                domain=domain,
                allow_any_model=True,
                quiet=True,
            )


def test_cmd_run_local_rejects_non_ollama_before_bench_import(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for key in list(sys.modules):
        if key == "bench" or key.startswith("bench."):
            del sys.modules[key]

    with pytest.raises(SystemExit) as exc:
        cli_main._cmd_run_local(
            argparse.Namespace(
                model="openai/gpt-4o",
                manifest="benchanything.json",
                domain_id=None,
                env_url="http://localhost:8765",
                episodes=1,
                seeds=None,
                system_prompt=None,
                temperature=0.0,
                max_tokens=512,
                parallel=1,
                quiet=True,
            )
        )
    assert exc.value.code == 1
    assert "Ollama" in capsys.readouterr().err
    assert "bench.models" not in sys.modules
