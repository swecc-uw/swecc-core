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


@pytest.mark.asyncio
async def test_list_runs_includes_cors_for_mesocosm(monkeypatch):
    async def fake_gallery_runs(*, domain_id=None, limit=50):
        return []

    monkeypatch.setattr(
        "bench_common.storage.database.list_gallery_runs",
        fake_gallery_runs,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/runs", headers={"Origin": MESOCOSM_ORIGIN})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == MESOCOSM_ORIGIN


@pytest.mark.asyncio
async def test_options_preflight_runs_post_for_mesocosm():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.options(
            "/v1/runs",
            headers={
                "Origin": MESOCOSM_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == MESOCOSM_ORIGIN
    allow_headers = (resp.headers.get("access-control-allow-headers") or "").lower()
    assert "authorization" in allow_headers
    assert "content-type" in allow_headers


@pytest.mark.asyncio
async def test_create_run_unauthorized_includes_cors_for_mesocosm(monkeypatch):
    monkeypatch.delenv("BENCH_AUTH_DISABLED", raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/runs",
            headers={"Origin": MESOCOSM_ORIGIN, "Content-Type": "application/json"},
            json={"domain_id": "example", "binding_vow_version": "1", "num_episodes": 1},
        )
    assert resp.status_code == 401
    assert resp.headers.get("access-control-allow-origin") == MESOCOSM_ORIGIN
