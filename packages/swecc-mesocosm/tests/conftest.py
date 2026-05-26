from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from swecc_mesocosm.client import BenchClient
from typer.testing import CliRunner


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


def _minimal_domain_payload_dict() -> dict[str, Any]:
    """Valid POST /v1/domains body for tests (no inference helpers)."""
    return {
        "id": "demo",
        "name": "Demo",
        "owner_id": "owner",
        "binding_vow": {
            "id": "demo-vow-1",
            "version": "1.0.0",
            "domain_id": "demo",
            "tier": "tier1",
            "description": "trivia quiz",
            "observation_space": {"type": "text", "description": "obs"},
            "action_space": {"type": "text", "description": "act"},
            "reward": {"type": "scalar", "description": "reward"},
            "episode": {"max_steps": 1, "supports_seed": True, "deterministic_reset": True},
            "techniques": [],
            "metadata": {"benchmark_kind": "qa_mcq"},
        },
        "endpoint": {"mode": "remote", "url": "https://example.com/env"},
        "scoring": {
            "primary_metric": "success_rate",
            "higher_is_better": True,
            "metrics": [
                {
                    "name": "success_rate",
                    "type": "terminal_field",
                    "field": "success",
                    "aggregation": "pass_rate",
                },
                {"name": "avg_reward", "type": "episode_reward", "aggregation": "mean"},
            ],
        },
        "tags": ["test"],
        "detail": "trivia quiz",
    }


@pytest.fixture
def minimal_domain_payload() -> dict[str, Any]:
    return _minimal_domain_payload_dict()


@pytest.fixture
def domain_json_file(tmp_path: Path, minimal_domain_payload: dict[str, Any]) -> Path:
    path = tmp_path / "domain.json"
    path.write_text(json.dumps(minimal_domain_payload), encoding="utf-8")
    return path


def bench_client_with_handler(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    base_url: str = "http://bench.test",
) -> BenchClient:
    client = BenchClient(base_url=base_url)
    client._client = httpx.AsyncClient(
        base_url=client._base,
        transport=httpx.MockTransport(handler),
    )
    return client
