from __future__ import annotations

import argparse
from unittest.mock import MagicMock

import httpx
import pytest
from bench_common.cli import main as cli_main


def _login_http_error(status: int, *, detail: str) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.swecc.org/auth/login/")
    response = httpx.Response(status, request=request, json={"detail": detail})
    return httpx.HTTPStatusError("Invalid username or password", request=request, response=response)


def _login_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "server_url": "https://api.example/",
        "bench_url": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_prompt_login_credentials_reads_username_and_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("bench_common.cli.main.getpass.getuser", lambda: "alice")
    monkeypatch.setattr("builtins.input", lambda _prompt: "alice")
    monkeypatch.setattr("bench_common.cli.main.getpass.getpass", lambda _prompt: "secret-from-tty")
    assert cli_main._prompt_login_credentials() == ("alice", "secret-from-tty")


def test_prompt_login_credentials_uses_os_user_when_username_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("bench_common.cli.main.getpass.getuser", lambda: "bob")
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    monkeypatch.setattr("bench_common.cli.main.getpass.getpass", lambda _prompt: "pass")
    assert cli_main._prompt_login_credentials() == ("bob", "pass")


def test_prompt_login_credentials_rejects_empty_username(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("bench_common.cli.main.getpass.getuser", lambda: "")
    monkeypatch.setattr("builtins.input", lambda _prompt: "   ")
    with pytest.raises(SystemExit) as exc_info:
        cli_main._prompt_login_credentials()
    assert exc_info.value.code == 1
    assert "Username cannot be empty" in capsys.readouterr().err


def test_prompt_login_credentials_rejects_empty_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("bench_common.cli.main.getpass.getuser", lambda: "alice")
    monkeypatch.setattr("builtins.input", lambda _prompt: "alice")
    monkeypatch.setattr("bench_common.cli.main.getpass.getpass", lambda _prompt: "")
    with pytest.raises(SystemExit) as exc_info:
        cli_main._prompt_login_credentials()
    assert exc_info.value.code == 1
    assert "Password cannot be empty" in capsys.readouterr().err


def test_cmd_auth_login_prompts_for_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("bench_common.cli.main.getpass.getuser", lambda: "")
    monkeypatch.setattr("builtins.input", lambda _prompt: "alice")
    monkeypatch.setattr("bench_common.cli.main.getpass.getpass", lambda _prompt: "tty-pass")
    login_mock = MagicMock()
    fetch_mock = MagicMock(return_value="jwt-token")
    save_mock = MagicMock()
    monkeypatch.setattr(cli_main, "login", login_mock)
    monkeypatch.setattr(cli_main, "fetch_jwt", fetch_mock)
    monkeypatch.setattr(cli_main, "save_credentials", save_mock)

    cli_main._cmd_auth_login(_login_args())

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
    monkeypatch.setattr(
        cli_main,
        "_prompt_login_credentials",
        lambda: ("bob", "cli-secret"),
    )
    monkeypatch.setattr(cli_main, "login", MagicMock())
    monkeypatch.setattr(cli_main, "fetch_jwt", MagicMock(return_value="jwt"))
    monkeypatch.setattr(cli_main, "save_credentials", MagicMock())

    cli_main._cmd_auth_login(_login_args(server_url=None))

    out, err = capsys.readouterr()
    assert "cli-secret" not in out
    assert "cli-secret" not in err


def test_cmd_auth_login_prints_friendly_message_on_bad_password(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli_main,
        "_prompt_login_credentials",
        lambda: ("navneethdg", "wrong-pass"),
    )
    monkeypatch.setattr(
        cli_main,
        "login",
        MagicMock(
            side_effect=_login_http_error(400, detail="Invalid credentials."),
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        cli_main._cmd_auth_login(_login_args(server_url="https://api.swecc.org"))
    assert exc_info.value.code == 1

    err = capsys.readouterr().err
    assert err.strip() == "Invalid username or password"
    assert "wrong-pass" not in err
    assert "Traceback" not in err


def test_cmd_auth_login_prints_jwt_error_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_main, "_prompt_login_credentials", lambda: ("alice", "secret"))
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

    with pytest.raises(SystemExit) as exc_info:
        cli_main._cmd_auth_login(_login_args(server_url="https://api.swecc.org"))
    assert exc_info.value.code == 1

    err = capsys.readouterr().err
    assert "Account access denied" in err
    assert "secret" not in err
    assert "Traceback" not in err


def test_auth_login_help_documents_interactive_prompts(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli_main.main(["auth", "login", "--help"])
    help_text = capsys.readouterr().out
    assert "--username" not in help_text
    assert "--password" not in help_text
    assert "Prompts for username and password" in help_text


def test_auth_login_rejects_unknown_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli_main.main(["auth", "login", "--username", "alice"])
    err = capsys.readouterr().err
    assert "unrecognized arguments" in err
