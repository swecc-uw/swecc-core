"""Behind SWAG, trailing-slash redirects must not drop the /bench gateway prefix."""

import pytest
from app.main import app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_trailing_slash_on_health_returns_404_not_redirect():
    transport = ASGITransport(app=app, root_path="/bench")
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/", follow_redirects=False)
    assert resp.status_code == 404
    assert "location" not in resp.headers
