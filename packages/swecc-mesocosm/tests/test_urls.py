from __future__ import annotations

import pytest
from swecc_mesocosm.urls import (
    default_bench_api_url,
    default_env_adapter_url,
    default_server_url,
    mesocosm_local_mode,
)


@pytest.fixture(autouse=True)
def _clear_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "MESOCOSM_BASE_URL",
        "MESOCOSM_LOCAL",
        "SWECC_BENCH_URL",
        "BENCH_API_URL",
        "SWECC_SERVER_URL",
        "MESOCOSM_ENV_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_default_bench_api_url_remote() -> None:
    assert default_bench_api_url() == "https://api.swecc.org/bench"


def test_default_bench_api_url_local_profile() -> None:
    import os

    os.environ["MESOCOSM_LOCAL"] = "1"
    assert default_bench_api_url() == "http://127.0.0.1:8010"
    del os.environ["MESOCOSM_LOCAL"]


def test_default_server_url_remote() -> None:
    assert default_server_url() == "https://api.swecc.org"


def test_default_env_adapter_url() -> None:
    assert default_env_adapter_url() == "http://127.0.0.1:8765"


def test_mesocosm_local_mode() -> None:
    import os

    os.environ["MESOCOSM_LOCAL"] = "true"
    assert mesocosm_local_mode() is True
    del os.environ["MESOCOSM_LOCAL"]
