"""CORS: Mesocosm SPA must receive Access-Control-Allow-Origin on success and errors."""

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient

MESOCOSM_ORIGIN = "https://mesocosm.swecc.org"


@pytest.mark.asyncio
async def test_health_includes_cors_for_mesocosm():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health", headers={"Origin": MESOCOSM_ORIGIN})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == MESOCOSM_ORIGIN
    assert resp.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_unauthorized_includes_cors_for_mesocosm(monkeypatch):
    monkeypatch.delenv("BENCH_AUTH_DISABLED", raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/me/context", headers={"Origin": MESOCOSM_ORIGIN})
    assert resp.status_code == 401
    assert resp.headers.get("access-control-allow-origin") == MESOCOSM_ORIGIN


@pytest.mark.asyncio
async def test_options_preflight_for_mesocosm():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.options(
            "/v1/domains",
            headers={
                "Origin": MESOCOSM_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == MESOCOSM_ORIGIN
