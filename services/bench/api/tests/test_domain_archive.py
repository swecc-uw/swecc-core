"""POST /v1/domains/{id}/archive is owner-only."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt


@pytest.fixture(scope="module")
def django_db():
    fd, db_path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.django_settings")
    os.environ.setdefault("DB_HOST", "localhost")
    os.environ.setdefault("DB_NAME", "test")
    os.environ.setdefault("DB_PORT", "5432")
    os.environ.setdefault("DB_USER", "test")
    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

    import django
    from django.conf import settings

    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": db_path,
    }
    django.setup()

    from django.core.management import call_command

    call_command("migrate", "bench", verbosity=0)

    yield

    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def api_app(django_db):
    from app.main import app

    return app


def _member_token(
    *,
    user_id: int,
    groups: list[str] | None = None,
) -> str:
    payload = {
        "user_id": user_id,
        "username": f"user-{user_id}",
        "groups": groups or ["is_authenticated"],
        "exp": 9999999999,
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


@pytest.fixture
def sample_domain():
    from bench_common.core.binding_vow import BindingVow
    from bench_common.core.domain import Domain, EnvironmentEndpoint
    from bench_common.core.scoring import MetricDef, ScoringConfig

    domain_id = "archive-route-test"
    vow = BindingVow(
        id=f"{domain_id}-vow",
        version="1.0.0",
        domain_id=domain_id,
        tier="tier1",
        description="test",
        observation_space={"type": "text", "description": "o"},
        action_space={"type": "text", "description": "a"},
        reward={"type": "scalar", "description": "r"},
        episode={"max_steps": 1, "supports_seed": True, "deterministic_reset": True},
        techniques=[],
    )
    return Domain(
        id=domain_id,
        name="Archive Route Test",
        owner_id="42",
        binding_vow=vow,
        endpoint=EnvironmentEndpoint(mode="remote", url="http://127.0.0.1:1"),
        scoring=ScoringConfig(
            primary_metric="score",
            higher_is_better=True,
            metrics=[MetricDef(name="score", type="episode_reward", aggregation="mean")],
        ),
        status="published",
    )


@pytest.mark.asyncio
async def test_archive_domain_owner_succeeds(api_app, sample_domain, monkeypatch):
    from bench_common.storage import django_store as store

    monkeypatch.delenv("BENCH_AUTH_DISABLED", raising=False)
    await store.save_domain(sample_domain)

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/v1/domains/{sample_domain.id}/archive",
            headers={"Authorization": f"Bearer {_member_token(user_id=42)}"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_archive_domain_non_owner_forbidden(api_app, sample_domain, monkeypatch):
    from bench_common.storage import django_store as store

    monkeypatch.delenv("BENCH_AUTH_DISABLED", raising=False)
    await store.save_domain(sample_domain)

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/v1/domains/{sample_domain.id}/archive",
            headers={"Authorization": f"Bearer {_member_token(user_id=99)}"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_archive_domain_bench_admin_forbidden(api_app, sample_domain, monkeypatch):
    from bench_common.storage import django_store as store

    monkeypatch.delenv("BENCH_AUTH_DISABLED", raising=False)
    await store.save_domain(sample_domain)

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/v1/domains/{sample_domain.id}/archive",
            headers={
                "Authorization": f"Bearer {_member_token(user_id=1, groups=['is_authenticated', 'is_admin'])}"
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_archive_legacy_string_owner_non_owner_forbidden(api_app, monkeypatch):
    from bench_common.core.binding_vow import BindingVow
    from bench_common.core.domain import Domain, EnvironmentEndpoint
    from bench_common.core.scoring import MetricDef, ScoringConfig
    from bench_common.storage import django_store as store

    monkeypatch.delenv("BENCH_AUTH_DISABLED", raising=False)
    domain_id = "legacy-smoke-domain"
    vow = BindingVow(
        id=f"{domain_id}-vow",
        version="1.0.0",
        domain_id=domain_id,
        tier="tier1",
        description="test",
        observation_space={"type": "text", "description": "o"},
        action_space={"type": "text", "description": "a"},
        reward={"type": "scalar", "description": "r"},
        episode={"max_steps": 1, "supports_seed": True, "deterministic_reset": True},
        techniques=[],
    )
    legacy = Domain(
        id=domain_id,
        name="Legacy",
        owner_id="smoke-owner",
        binding_vow=vow,
        endpoint=EnvironmentEndpoint(mode="remote", url="http://127.0.0.1:1"),
        scoring=ScoringConfig(
            primary_metric="score",
            higher_is_better=True,
            metrics=[MetricDef(name="score", type="episode_reward", aggregation="mean")],
        ),
        status="published",
    )
    await store.save_domain(legacy)

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/v1/domains/{domain_id}/archive",
            headers={"Authorization": f"Bearer {_member_token(user_id=42)}"},
        )
    assert resp.status_code == 403
