from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from swecc_mesocosm.client import BenchClient
from swecc_mesocosm.infer import build_domain_payload


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def minimal_domain_payload() -> dict[str, Any]:
    return build_domain_payload(
        benchmark_id="demo",
        name="Demo",
        owner_id="owner",
        description="trivia quiz",
        env_url="https://example.com/env",
    )


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
