from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from bench_common.cli import main as cli_main
from bench_common.cli.urls import (
    bench_url_from_server,
    guest_bench_api_url,
    member_bench_api_url,
    whoami_bench_api_url,
)


@pytest.fixture(autouse=True)
def _clear_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("MESOCOSM_BASE_URL", "MESOCOSM_LOCAL", "SWECC_BENCH_URL", "BENCH_API_URL"):
        monkeypatch.delenv(key, raising=False)


def test_guest_bench_api_url_prod_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESOCOSM_LOCAL", "1")
    assert guest_bench_api_url() == "https://api.swecc.org/bench"


def test_guest_bench_api_url_respects_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESOCOSM_LOCAL", "1")
    monkeypatch.setenv("SWECC_BENCH_URL", "http://127.0.0.1:8010")
    assert guest_bench_api_url() == "http://127.0.0.1:8010"


def test_bench_url_for_guest_ignores_saved_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESOCOSM_LOCAL", "1")
    args = argparse.Namespace(bench_url=None)
    with patch.object(cli_main, "load_credentials", return_value={"bench_url": "http://127.0.0.1:8010"}):
        assert cli_main._bench_url_for_guest(args) == "https://api.swecc.org/bench"


def test_bench_url_for_guest_cli_flag_wins() -> None:
    args = argparse.Namespace(bench_url="http://custom:9999/")
    assert cli_main._bench_url_for_guest(args) == "http://custom:9999"


def test_bench_url_uses_saved_creds_when_consistent() -> None:
    args = argparse.Namespace(bench_url=None)
    creds = {"bench_url": "http://127.0.0.1:8010", "server_url": "http://127.0.0.1:8000"}
    with patch.object(cli_main, "load_credentials", return_value=creds):
        assert cli_main._bench_url(args) == "http://127.0.0.1:8010"


def test_bench_url_ignores_stale_local_with_prod_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESOCOSM_LOCAL", "1")
    args = argparse.Namespace(bench_url=None)
    creds = {
        "bench_url": "http://127.0.0.1:8010",
        "server_url": "https://api.swecc.org",
        "mode": "member",
    }
    with patch.object(cli_main, "load_credentials", return_value=creds):
        assert cli_main._bench_url(args) == "https://api.swecc.org/bench"


def test_member_bench_api_url_prod_login_ignores_mesocosm_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MESOCOSM_LOCAL", "1")
    assert (
        member_bench_api_url(server_url="https://api.swecc.org")
        == "https://api.swecc.org/bench"
    )


def test_bench_url_from_server_prod() -> None:
    assert bench_url_from_server("https://api.swecc.org") == "https://api.swecc.org/bench"


def test_whoami_guest_uses_saved_bench_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESOCOSM_LOCAL", "1")
    creds = {
        "mode": "guest",
        "bench_url": "https://api.swecc.org/bench",
        "token": "tok",
    }
    assert whoami_bench_api_url(creds=creds) == "https://api.swecc.org/bench"


def test_cmd_auth_guest_connect_error_exits(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = argparse.Namespace(bench_url=None)

    def _raise_connect(*_a, **_k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(cli_main.httpx, "post", _raise_connect)
    with pytest.raises(SystemExit) as exc:
        cli_main._cmd_auth_guest(args)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "https://api.swecc.org/bench" in err
    assert "MESOCOSM_LOCAL" in err


def test_cmd_auth_whoami_connect_error_exits(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = argparse.Namespace(bench_url=None)
    creds = {"mode": "member", "token": "t", "bench_url": "http://127.0.0.1:8010"}

    class _FakeSession:
        def __enter__(self):
            raise httpx.ConnectError("connection refused")

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(cli_main, "load_credentials", lambda: creds)
    monkeypatch.setattr(cli_main, "get_bench_session", lambda **_k: _FakeSession())
    with pytest.raises(SystemExit) as exc:
        cli_main._cmd_auth_whoami(args)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "connection refused" in err


def test_cmd_auth_whoami_guest_anonymous_exits(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = argparse.Namespace(bench_url=None)
    creds = {
        "mode": "guest",
        "token": "guest-tok",
        "bench_url": "https://api.swecc.org/bench",
    }
    response = MagicMock()
    response.json.return_value = {"type": "anonymous"}
    response.raise_for_status = MagicMock()

    class _FakeSession:
        client = MagicMock(get=MagicMock(return_value=response))

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(cli_main, "load_credentials", lambda: creds)
    monkeypatch.setattr(cli_main, "get_bench_session", lambda **_k: _FakeSession())
    with pytest.raises(SystemExit) as exc:
        cli_main._cmd_auth_whoami(args)
    assert exc.value.code == 1
    assert "Guest token was not recognized" in capsys.readouterr().err


def test_cmd_auth_whoami_prints_member(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    args = argparse.Namespace(bench_url=None)
    creds = {
        "mode": "member",
        "token": "jwt",
        "server_url": "https://api.swecc.org",
        "bench_url": "https://api.swecc.org/bench",
    }
    me = {"type": "member", "user_id": 1, "username": "alice"}
    response = MagicMock()
    response.json.return_value = me
    response.raise_for_status = MagicMock()

    class _FakeSession:
        client = MagicMock(get=MagicMock(return_value=response))

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(cli_main, "load_credentials", lambda: creds)
    monkeypatch.setattr(cli_main, "get_bench_session", lambda **_k: _FakeSession())
    cli_main._cmd_auth_whoami(args)
    out = json.loads(capsys.readouterr().out)
    assert out == me
