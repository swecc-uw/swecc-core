"""CLI auth/session edge cases — friendly errors without tracebacks."""

from __future__ import annotations

import argparse
import getpass
import warnings
from unittest.mock import MagicMock, patch

import httpx
import pytest

from bench_common.cli import main as cli_main


def test_auth_whoami_without_credentials_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "load_credentials", lambda: None)
    monkeypatch.delenv("SWECC_BENCH_TOKEN", raising=False)
    monkeypatch.delenv("SWECC_BENCH_GUEST_TOKEN", raising=False)

    with pytest.raises(SystemExit) as exc:
        cli_main._cmd_auth_whoami(argparse.Namespace(bench_url=None))
    assert exc.value.code == 1

    err = capsys.readouterr().err
    assert "Not authenticated" in err
    assert "mesocosm auth login" in err
    assert "Traceback" not in err


def test_team_list_without_credentials_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "load_credentials", lambda: None)

    with pytest.raises(SystemExit) as exc:
        cli_main._cmd_team_list(argparse.Namespace(bench_url=None))
    assert exc.value.code == 1

    err = capsys.readouterr().err
    assert "Not authenticated" in err
    assert "Traceback" not in err


def test_run_export_404_prints_friendly_error(capsys: pytest.CaptureFixture[str]) -> None:
    request = httpx.Request("GET", "https://api.swecc.org/bench/v1/runs/fake/export")
    response = httpx.Response(404, request=request, json={"detail": "Run not found"})
    response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("404", request=request, response=response)
    )
    session = MagicMock()
    session.client.get.return_value = response
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)

    with patch.object(cli_main, "_get_bench_session_or_exit", return_value=session):
        with pytest.raises(SystemExit) as exc:
            cli_main._cmd_run_export(argparse.Namespace(run_id="fake", output=None, bench_url=None))
    assert exc.value.code == 1

    err = capsys.readouterr().err
    assert "404" in err
    assert "Run not found" in err
    assert "Traceback" not in err


def test_prompt_login_suppresses_getpass_warning_when_not_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_main.getpass, "getuser", lambda: "alice")
    monkeypatch.setattr("builtins.input", lambda _prompt: "alice")
    monkeypatch.setattr(cli_main.getpass, "getpass", lambda _prompt: "secret")
    monkeypatch.setattr(cli_main.sys.stdin, "isatty", lambda: False)

    with warnings.catch_warnings(record=True) as caught:
        user, password = cli_main._prompt_login_credentials()
    assert user == "alice"
    assert password == "secret"
    assert not any(issubclass(w.category, getpass.GetPassWarning) for w in caught)
