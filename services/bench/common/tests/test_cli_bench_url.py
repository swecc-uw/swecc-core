from __future__ import annotations

import argparse
from unittest.mock import patch

import httpx
import pytest

from bench_common.cli import main as cli_main
from bench_common.cli.urls import guest_bench_api_url


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


def test_bench_url_uses_saved_creds() -> None:
    args = argparse.Namespace(bench_url=None)
    with patch.object(cli_main, "load_credentials", return_value={"bench_url": "http://127.0.0.1:8010"}):
        assert cli_main._bench_url(args) == "http://127.0.0.1:8010"


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
