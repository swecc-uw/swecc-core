"""PATCH /v1/runs/{run_id}/visibility for run owners."""

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


def _sample_domain(domain_id: str = "toggle-visibility-domain"):
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
        name="Toggle Visibility Test",
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


def _sample_run(domain_id: str, run_id: str = "toggle-run-1"):
    from bench_common.core.run import AgentConfig, Run, RunConfig

    return Run(
        id=run_id,
        config=RunConfig(
            domain_id=domain_id,
            binding_vow_version="1.0.0",
            agent_config=AgentConfig(model="test/model"),
        ),
        requester_id="1",
        status="completed",
        scores={"score": 1.0},
    )


@pytest.mark.asyncio
async def test_patch_run_visibility_owner(api_app, monkeypatch):
    from bench.models import ActorType, Visibility
    from bench_common.storage import django_store as store

    monkeypatch.setenv("BENCH_AUTH_DISABLED", "0")

    domain = _sample_domain()
    run = _sample_run(domain.id)
    await store.save_domain(domain)
    await store.save_run(
        run,
        actor_type=ActorType.MEMBER,
        actor_id="1",
        visibility=Visibility.GALLERY_PUBLIC,
    )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.patch(
            f"/v1/runs/{run.id}/visibility",
            headers={"Authorization": f"Bearer {_member_token(user_id=1)}"},
            json={"visibility": "private"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == run.id
    assert body["visibility"] == "private"


@pytest.mark.asyncio
async def test_patch_run_visibility_forbidden_for_other_member(api_app, monkeypatch):
    from bench.models import ActorType, Visibility
    from bench_common.storage import django_store as store

    monkeypatch.setenv("BENCH_AUTH_DISABLED", "0")

    domain = _sample_domain()
    run = _sample_run(domain.id)
    await store.save_domain(domain)
    await store.save_run(
        run,
        actor_type=ActorType.MEMBER,
        actor_id="1",
        visibility=Visibility.GALLERY_PUBLIC,
    )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.patch(
            f"/v1/runs/{run.id}/visibility",
            headers={"Authorization": f"Bearer {_member_token(user_id=2)}"},
            json={"visibility": "private"},
        )

    assert resp.status_code == 403
