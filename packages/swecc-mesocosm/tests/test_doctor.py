from __future__ import annotations

import json

import httpx
import pytest
from swecc_mesocosm.cli import _probe_url, app
from typer.testing import CliRunner


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


def test_probe_url_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "swecc_mesocosm.cli.httpx.get",
        lambda url, timeout=10.0: httpx.Response(200, json={"ok": True}),
    )
    code, err = _probe_url("http://bench.test/health")
    assert code == 200
    assert err is None


def test_doctor_ok(cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, timeout: float = 10.0) -> httpx.Response:
        if url.endswith("/health"):
            return httpx.Response(200, json={"status": "ok"})
        if url.endswith("/openapi.json"):
            return httpx.Response(200, json={"openapi": "3.1.0"})
        return httpx.Response(404)

    monkeypatch.setattr("swecc_mesocosm.cli.httpx.get", fake_get)
    result = cli_runner.invoke(app, ["doctor", "--base-url", "http://bench.test/bench"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_doctor_fails_when_health_down(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "swecc_mesocosm.cli.httpx.get",
        lambda url, timeout=10.0: httpx.Response(503, json={"detail": "down"}),
    )
    result = cli_runner.invoke(app, ["doctor", "--base-url", "http://bench.test/bench"])
    assert result.exit_code == 1


def test_doctor_local_ok_when_adapter_healthy(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, timeout: float = 10.0) -> httpx.Response:
        if "8765" in url:
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(503, json={"detail": "bench down"})

    monkeypatch.setattr("swecc_mesocosm.cli.httpx.get", fake_get)
    result = cli_runner.invoke(app, ["doctor", "--local", "--base-url", "http://bench.test/bench"])
    assert result.exit_code == 0, result.stdout
    body = json.loads(result.stdout)
    assert body["profile"] == "local"
    assert body["ok"] is True
    assert body["env_adapter"]["status_code"] == 200
