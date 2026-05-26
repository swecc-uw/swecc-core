from __future__ import annotations

import argparse
import warnings
from unittest.mock import MagicMock, patch

import pytest

from bench_common.cli import main as cli_main


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


def test_auth_login_help_documents_secure_password(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli_main.main(["auth", "login", "--help"])
    help_text = capsys.readouterr().out
    assert "--password" in help_text
    assert "deprecated" in help_text.lower() or "prompt" in help_text.lower()
    assert "[--password" in help_text
