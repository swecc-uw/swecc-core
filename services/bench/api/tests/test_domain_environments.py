"""GET /v1/domains/{domain_id}/environments mirrors developer list by domain."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt


def _member_token(*, user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "username": f"user-{user_id}",
        "groups": ["is_authenticated"],
        "exp": 9999999999,
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


def _sample_domain(domain_id: str = "domain-env-list"):
    from bench_common.core.binding_vow import BindingVow
    from bench_common.core.domain import Domain, EnvironmentEndpoint
    from bench_common.core.scoring import MetricDef, ScoringConfig

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
        name="Domain Env List",
        owner_id="1",
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
async def test_domain_environments_matches_developer_list(api_app, monkeypatch):
    from bench.models import ActorType, EnvScope
    from bench_common.storage import django_store as store

    monkeypatch.setenv("BENCH_AUTH_DISABLED", "0")
    domain = _sample_domain()
    await store.save_domain(domain)
    env_id = "solo-env-domain"
    await store.save_developer_environment(
        {
            "id": env_id,
            "owner_id": "1",
            "name": "My Env",
            "github_url": "https://github.com/org/repo",
            "status": "ready",
            "domain_id": domain.id,
            "env_url": "http://sandbox/envs/x",
            "scope": EnvScope.SOLO,
            "actor_type": ActorType.MEMBER,
            "actor_id": "1",
        }
    )

    headers = {"Authorization": f"Bearer {_member_token(user_id=1)}"}
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        domain_resp = await client.get(f"/v1/domains/{domain.id}/environments", headers=headers)
        dev_resp = await client.get(
            "/v1/developer/environments",
            params={"domain_id": domain.id},
            headers=headers,
        )

    assert domain_resp.status_code == 200
    assert dev_resp.status_code == 200
    slim = domain_resp.json()
    full = dev_resp.json()
    assert len(slim) == 1
    assert len(full) == 1
    assert slim[0]["id"] == env_id
    assert set(slim[0].keys()) == {
        "id",
        "name",
        "status",
        "domain_id",
        "env_url",
        "scope",
        "team_id",
    }
    assert slim[0]["name"] == full[0]["name"]
    assert slim[0]["domain_id"] == domain.id


@pytest.mark.asyncio
async def test_domain_environments_404_unknown_domain(api_app, monkeypatch):
    monkeypatch.setenv("BENCH_AUTH_DISABLED", "0")
    headers = {"Authorization": f"Bearer {_member_token(user_id=1)}"}
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/domains/missing-domain/environments", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mirror_developer_env_sets_actor_for_legacy_row(api_app):
    from bench.models import DeveloperEnvironment, EnvScope
    from bench_common.storage import django_store as store
    from bench_common.storage.dev_sync import mirror_developer_env_from_domain

    domain = _sample_domain("legacy-mirror-domain")
    await store.save_domain(domain)
    await DeveloperEnvironment.objects.acreate(
        id=domain.id,
        owner_id=domain.owner_id,
        name=domain.name,
        github_url="",
        status="ready",
        domain_id=domain.id,
        actor_id=None,
        scope="",
    )
    await mirror_developer_env_from_domain(domain)
    row = await DeveloperEnvironment.objects.aget(id=domain.id)
    assert row.actor_id == domain.owner_id
    assert row.scope == EnvScope.SOLO
