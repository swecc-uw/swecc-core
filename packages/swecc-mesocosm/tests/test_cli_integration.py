from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from swecc_mesocosm.cli import app
from tests.conftest import bench_client_with_handler
from typer.testing import CliRunner


@pytest.fixture
def patch_bench_client(monkeypatch: pytest.MonkeyPatch):
    def _patch(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        def factory(base_url: str | None = None) -> Any:
            return bench_client_with_handler(
                handler,
                base_url=base_url or "http://bench.test",
            )

        monkeypatch.setattr("swecc_mesocosm.cli._client", factory)

    return _patch


def test_eval_test_episode(cli_runner: CliRunner, patch_bench_client: Any) -> None:
    episode = {"id": "ep-1", "status": "completed", "reward": 1.0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1/test/episode")
        body = json.loads(request.content.decode())
        assert body["domain_id"] == "demo"
        assert body["binding_vow_version"] == "1.0.0"
        return httpx.Response(200, json=episode)

    patch_bench_client(handler)
    result = cli_runner.invoke(
        app,
        [
            "eval",
            "test",
            "--domain-id",
            "demo",
            "--vow-version",
            "1.0.0",
            "--model",
            "openai/gpt-4o-mini",
            "--base-url",
            "http://bench.test",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["id"] == "ep-1"


def test_eval_test_episode_fails_on_failed_status(
    cli_runner: CliRunner,
    patch_bench_client: Any,
) -> None:
    episode = {"id": "ep-1", "status": "failed", "terminal_info": {"error": "boom"}}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/test/episode"):
            return httpx.Response(200, json=episode)
        return httpx.Response(404)

    patch_bench_client(handler)
    result = cli_runner.invoke(
        app,
        [
            "eval",
            "test",
            "--domain-id",
            "demo",
            "--vow-version",
            "1.0.0",
            "--model",
            "openai/gpt-4o-mini",
            "--base-url",
            "http://bench.test",
        ],
    )
    assert result.exit_code == 1
    assert "failed" in result.stderr


def test_eval_test_resolves_vow_version_from_domain(
    cli_runner: CliRunner,
    patch_bench_client: Any,
) -> None:
    domain = {
        "id": "demo",
        "status": "draft",
        "binding_vow": {"version": "2.1.0", "domain_id": "demo"},
    }
    episode = {"id": "ep-1", "status": "completed"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/v1/domains/demo"):
            return httpx.Response(200, json=domain)
        body = json.loads(request.content.decode())
        assert body["binding_vow_version"] == "2.1.0"
        return httpx.Response(200, json=episode)

    patch_bench_client(handler)
    result = cli_runner.invoke(
        app,
        [
            "eval",
            "test",
            "--domain-id",
            "demo",
            "--model",
            "openai/gpt-4o-mini",
            "--base-url",
            "http://bench.test",
        ],
    )
    assert result.exit_code == 0, result.stderr


def test_eval_run_rejects_unpublished_domain(
    cli_runner: CliRunner,
    patch_bench_client: Any,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"id": "demo", "status": "draft"})
        return httpx.Response(500)

    patch_bench_client(handler)
    result = cli_runner.invoke(
        app,
        [
            "eval",
            "run",
            "--domain-id",
            "demo",
            "--vow-version",
            "1.0.0",
            "--model",
            "openai/gpt-4o-mini",
            "--base-url",
            "http://bench.test",
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == "domain_not_published"


def test_eval_run_allow_draft(
    cli_runner: CliRunner,
    patch_bench_client: Any,
) -> None:
    run = {"run_id": "run-1", "status": "queued"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/v1/runs"):
            return httpx.Response(200, json=run)
        return httpx.Response(404)

    patch_bench_client(handler)
    result = cli_runner.invoke(
        app,
        [
            "eval",
            "run",
            "--domain-id",
            "demo",
            "--vow-version",
            "1.0.0",
            "--model",
            "openai/gpt-4o-mini",
            "--allow-draft",
            "--base-url",
            "http://bench.test",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["run_id"] == "run-1"


def test_run_get(cli_runner: CliRunner, patch_bench_client: Any) -> None:
    run = {"id": "run-1", "scores": {"success_rate": 0.5}}
    episodes = [{"id": "ep-1"}]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/episodes"):
            return httpx.Response(200, json=episodes)
        return httpx.Response(200, json=run)

    patch_bench_client(handler)
    result = cli_runner.invoke(
        app,
        ["run", "get", "run-1", "--base-url", "http://bench.test"],
    )
    assert result.exit_code == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["run"]["id"] == "run-1"
    assert body["episodes"] == episodes
    assert body["aggregate_scores"] == run["scores"]


def test_run_episodes_with_traces(cli_runner: CliRunner, patch_bench_client: Any) -> None:
    episodes = [{"id": "ep-1"}]
    traces = {"ep-1": {"steps": []}}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/traces"):
            return httpx.Response(200, json=traces)
        return httpx.Response(200, json=episodes)

    patch_bench_client(handler)
    result = cli_runner.invoke(
        app,
        ["run", "episodes", "run-1", "--traces", "--base-url", "http://bench.test"],
    )
    assert result.exit_code == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["traces_by_episode"] == traces


def test_cli_http_error_json(
    cli_runner: CliRunner,
    patch_bench_client: Any,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "missing"})

    patch_bench_client(handler)
    result = cli_runner.invoke(
        app,
        ["run", "get", "missing", "--base-url", "http://bench.test"],
    )
    assert result.exit_code == 1
    body = json.loads(result.stdout)
    assert body["error"] == "http_error"
    assert body["status_code"] == 404
