from __future__ import annotations

import httpx
import pytest
from swecc_mesocosm.client import BenchClient


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
