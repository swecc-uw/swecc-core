from __future__ import annotations

import httpx
import pytest
from swecc_mesocosm.client import BenchClient, _auth_headers


@pytest.mark.asyncio
async def test_client_respects_base_url_path_prefix() -> None:
    urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json=[])

    client = BenchClient(base_url="https://api.example.com/bench")
    client._client = httpx.AsyncClient(
        base_url=client._base,
        transport=httpx.MockTransport(handler),
    )
    await client.list_domains()
    await client.aclose()
    assert urls == ["https://api.example.com/bench/v1/domains"]


def test_auth_headers_prefer_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SWECC_BENCH_TOKEN", "env-token")
    assert _auth_headers() == {"Authorization": "Bearer env-token"}


def test_auth_headers_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCH_AUTH_DISABLED", "1")
    monkeypatch.setenv("SWECC_BENCH_TOKEN", "env-token")
    assert _auth_headers() == {}


def test_bench_client_attaches_auth_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SWECC_BENCH_TOKEN", "cli-token")
    client = BenchClient(base_url="https://api.example.com/bench")
    assert client._client.headers["Authorization"] == "Bearer cli-token"


@pytest.mark.asyncio
async def test_bench_client_sends_auth_on_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SWECC_BENCH_TOKEN", "cli-token")
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json=[])

    client = BenchClient(base_url="https://api.example.com/bench")
    client._client = httpx.AsyncClient(
        base_url=client._base,
        headers=client._client.headers,
        transport=httpx.MockTransport(handler),
    )
    await client.list_domains()
    await client.aclose()
    assert seen == ["Bearer cli-token"]
