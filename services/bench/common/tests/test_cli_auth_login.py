from __future__ import annotations

import argparse
import warnings
from unittest.mock import MagicMock, patch

import httpx
import pytest

from bench_common.cli import main as cli_main


def _login_http_error(status: int, *, detail: str) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.swecc.org/auth/login/")
    response = httpx.Response(status, request=request, json={"detail": detail})
    return httpx.HTTPStatusError("Invalid username or password", request=request, response=response)


def test_resolve_login_password_prompts_when_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bench_common.cli.main.getpass.getpass", lambda _prompt: "secret-from-tty")
    args = argparse.Namespace(password=None)
    assert cli_main._resolve_login_password(args) == "secret-from-tty"


def test_resolve_login_password_deprecates_cli_flag() -> None:
    args = argparse.Namespace(password="from-argv")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert cli_main._resolve_login_password(args) == "from-argv"
    assert len(caught) == 1
    assert issubclass(caught[0].category, DeprecationWarning)
    assert "--password" in str(caught[0].message)


def test_cmd_auth_login_uses_getpass_not_argv_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("bench_common.cli.main.getpass.getpass", lambda _prompt: "tty-pass")
    login_mock = MagicMock()
    fetch_mock = MagicMock(return_value="jwt-token")
    save_mock = MagicMock()
    monkeypatch.setattr(cli_main, "login", login_mock)
    monkeypatch.setattr(cli_main, "fetch_jwt", fetch_mock)
    monkeypatch.setattr(cli_main, "save_credentials", save_mock)

    args = argparse.Namespace(
        server_url="https://api.example/",
        username="alice",
        password=None,
        bench_url=None,
    )
    cli_main._cmd_auth_login(args)

    login_mock.assert_called_once()
    assert login_mock.call_args[0][2:4] == ("alice", "tty-pass")
    save_mock.assert_called_once()
    out = capsys.readouterr().out
    assert "Logged in" in out
    assert "tty-pass" not in out


def test_cmd_auth_login_never_prints_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "login", MagicMock())
    monkeypatch.setattr(cli_main, "fetch_jwt", MagicMock(return_value="jwt"))
    monkeypatch.setattr(cli_main, "save_credentials", MagicMock())

    args = argparse.Namespace(
        server_url=None,
        username="bob",
        password="cli-secret",
        bench_url=None,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        cli_main._cmd_auth_login(args)

    out, err = capsys.readouterr()
    assert "cli-secret" not in out
    assert "cli-secret" not in err


def test_cmd_auth_login_prints_friendly_message_on_bad_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("bench_common.cli.main.getpass.getpass", lambda _prompt: "wrong-pass")
    monkeypatch.setattr(
        cli_main,
        "login",
        MagicMock(
            side_effect=_login_http_error(400, detail="Invalid credentials."),
        ),
    )

    args = argparse.Namespace(
        server_url="https://api.swecc.org",
        username="navneethdg",
        password=None,
        bench_url=None,
    )
    with pytest.raises(SystemExit) as exc_info:
        cli_main._cmd_auth_login(args)
    assert exc_info.value.code == 1

    err = capsys.readouterr().err
    assert err.strip() == "Invalid username or password"
    assert "wrong-pass" not in err
    assert "Traceback" not in err


def test_cmd_auth_login_prints_jwt_error_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("bench_common.cli.main.getpass.getpass", lambda _prompt: "secret")
    monkeypatch.setattr(cli_main, "login", MagicMock())
    jwt_request = httpx.Request("GET", "https://api.swecc.org/auth/jwt/")
    jwt_response = httpx.Response(
        403,
        request=jwt_request,
        json={"detail": "Authentication credentials were not provided."},
    )
    monkeypatch.setattr(
        cli_main,
        "fetch_jwt",
        MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Account access denied: Authentication credentials were not provided.",
                request=jwt_request,
                response=jwt_response,
            )
        ),
    )

    args = argparse.Namespace(
        server_url="https://api.swecc.org",
        username="alice",
        password=None,
        bench_url=None,
    )
    with pytest.raises(SystemExit) as exc_info:
        cli_main._cmd_auth_login(args)
    assert exc_info.value.code == 1

    err = capsys.readouterr().err
    assert "Account access denied" in err
    assert "secret" not in err
    assert "Traceback" not in err


def test_auth_login_help_documents_secure_password(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli_main.main(["auth", "login", "--help"])
    help_text = capsys.readouterr().out
    assert "--password" in help_text
    assert "deprecated" in help_text.lower() or "prompt" in help_text.lower()
    assert "[--password" in help_text
