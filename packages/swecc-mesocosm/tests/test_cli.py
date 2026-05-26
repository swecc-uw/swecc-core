from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
import pytest
from rich.console import Console
from swecc_mesocosm import __version__
from swecc_mesocosm.cli import _connection_error_payload, _http_error_payload, app, main
from swecc_mesocosm.help_text import print_root_help, print_run_help
from typer.testing import CliRunner


def test_version_flag(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"mesocosm {__version__}"


def test_root_help_lists_auth_and_env_commands() -> None:
    buf = StringIO()
    print_root_help(console=Console(file=buf, width=120, force_terminal=False))
    out = buf.getvalue()
    assert "auth login" in out
    assert "env submit" in out
    assert "run local" in out
    assert "run get" in out
    assert "doctor" in out
    assert "validate FILE" in out
    assert "suggest" not in out
    assert "publish ID" not in out
    assert "register domain.py" in out
    assert "register\n" not in out or "register domain.py" in out


def test_run_help_lists_platform_and_inspection() -> None:
    buf = StringIO()
    print_run_help(console=Console(file=buf, width=120, force_terminal=False))
    out = buf.getvalue()
    assert "run create" in out or "create" in out
    assert "local" in out
    assert "get RUN_ID" in out or "get" in out


def test_main_help_entrypoint(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["mesocosm", "--help"])
    main()
    assert "auth login" in capsys.readouterr().out


def test_validate_ok_from_file(cli_runner: CliRunner, domain_json_file: Path) -> None:
    result = cli_runner.invoke(app, ["validate", str(domain_json_file)])
    assert result.exit_code == 0
    body = json.loads(result.stdout)
    assert body["ok"] is True


def test_validate_ok_from_stdin(
    cli_runner: CliRunner,
    minimal_domain_payload: dict[str, Any],
) -> None:
    result = cli_runner.invoke(
        app,
        ["validate", "-"],
        input=json.dumps(minimal_domain_payload),
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["ok"] is True


def test_validate_missing_file(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(app, ["validate", "/no/such/domain.json"])
    assert result.exit_code == 1
    assert "no such file" in result.stderr


def test_validate_invalid_json(cli_runner: CliRunner, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = cli_runner.invoke(app, ["validate", str(bad)])
    assert result.exit_code == 1
    assert "invalid JSON" in result.stderr


def test_validate_fails_on_policy_violation(
    cli_runner: CliRunner,
    minimal_domain_payload: dict[str, Any],
    tmp_path: pytest.TempPathFactory,
) -> None:
    payload = {**minimal_domain_payload}
    del payload["name"]
    path = tmp_path / "domain.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = cli_runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False


def test_eval_run_invalid_seed_set(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(
        app,
        [
            "eval",
            "run",
            "--domain-id",
            "d",
            "--vow-version",
            "1.0.0",
            "--model",
            "openai/gpt-4o-mini",
            "--seed-set",
            "not-json",
        ],
    )
    assert result.exit_code == 1
    assert "--seed-set must be" in result.stderr


def test_http_error_payload() -> None:
    request = httpx.Request("GET", "http://bench.test/v1/domains/x")
    response = httpx.Response(404, json={"detail": "not found"}, request=request)
    exc = httpx.HTTPStatusError("404", request=request, response=response)
    payload = _http_error_payload(exc)
    assert payload["error"] == "http_error"
    assert payload["status_code"] == 404
    assert payload["detail"] == {"detail": "not found"}


def test_http_error_payload_non_json_body() -> None:
    request = httpx.Request("GET", "http://bench.test/v1/domains/x")
    response = httpx.Response(500, text="internal error", request=request)
    exc = httpx.HTTPStatusError("500", request=request, response=response)
    payload = _http_error_payload(exc)
    assert payload["detail"] == "internal error"


def test_connection_error_payload() -> None:
    request = httpx.Request("GET", "http://bench.test/v1/domains")
    exc = httpx.ConnectError("connection refused", request=request)
    payload = _connection_error_payload(exc)
    assert payload["error"] == "connection_error"
    assert payload["url"] == "http://bench.test/v1/domains"
    assert "MESOCOSM_BASE_URL" in payload["hint"]
