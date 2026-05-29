"""GET /v1/runs?env_id= lists all env runs for members with dev env access."""

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


def _sample_domain(domain_id: str = "env-runs-domain"):
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
        name="Env Runs",
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


def _sample_run(domain_id: str, run_id: str, *, env_id: str):
    from bench_common.core.run import AgentConfig, Run, RunConfig

    return Run(
        id=run_id,
        config=RunConfig(
            domain_id=domain_id,
            binding_vow_version="1.0.0",
            agent_config=AgentConfig(model="test/model"),
            env_id=env_id,
        ),
        requester_id="1",
        status="completed",
        env_id=env_id,
    )


@pytest.mark.asyncio
async def test_list_runs_env_id_includes_all_team_members_runs(api_app, monkeypatch):
    from app.services import run_list as run_list_svc
    from app.services import teams as team_svc
    from bench.models import ActorType, EnvScope
    from bench_common.storage import django_store as store

    monkeypatch.setenv("BENCH_AUTH_DISABLED", "0")

    async def _fake_usernames(user_ids: list[int]) -> dict[str, str]:
        return {str(uid): f"user-{uid}" for uid in user_ids}

    monkeypatch.setattr(run_list_svc, "member_usernames_by_id", _fake_usernames)

    domain = _sample_domain()
    await store.save_domain(domain)
    team = await team_svc.create_team(name="Bench Team", owner_user_id=1)
    await team_svc.join_team_by_code(code=team.join_code, user_id=2)

    env_id = "team-env-1"
    await store.save_developer_environment(
        {
            "id": env_id,
            "owner_id": "1",
            "name": "Shared",
            "github_url": "https://github.com/org/repo",
            "status": "ready",
            "domain_id": domain.id,
            "scope": EnvScope.TEAM,
            "actor_type": ActorType.MEMBER,
            "actor_id": "1",
            "team_id": str(team.id),
            "created_by_user_id": 1,
        }
    )

    await store.save_run(
        _sample_run(domain.id, "run-user-1", env_id=env_id),
        actor_type=ActorType.MEMBER,
        actor_id="1",
    )
    await store.save_run(
        _sample_run(domain.id, "run-user-2", env_id=env_id),
        actor_type=ActorType.MEMBER,
        actor_id="2",
    )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/v1/runs",
            params={"env_id": env_id},
            headers={"Authorization": f"Bearer {_member_token(user_id=1)}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert {r["id"] for r in body} == {"run-user-1", "run-user-2"}
    by_actor = {r["actor_id"]: r for r in body}
    assert by_actor["1"]["actor_username"] == "user-1"
    assert by_actor["2"]["actor_username"] == "user-2"
    assert all(r["actor_type"] == ActorType.MEMBER for r in body)


@pytest.mark.asyncio
async def test_list_runs_without_env_id_still_filters_to_caller(api_app, monkeypatch):
    from bench.models import ActorType
    from bench_common.storage import django_store as store

    monkeypatch.setenv("BENCH_AUTH_DISABLED", "0")
    domain = _sample_domain("solo-filter-domain")
    await store.save_domain(domain)
    await store.save_run(
        _sample_run(domain.id, "mine", env_id="env-a"),
        actor_type=ActorType.MEMBER,
        actor_id="1",
    )
    await store.save_run(
        _sample_run(domain.id, "theirs", env_id="env-a"),
        actor_type=ActorType.MEMBER,
        actor_id="2",
    )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/v1/runs",
            params={"domain_id": domain.id},
            headers={"Authorization": f"Bearer {_member_token(user_id=1)}"},
        )
    assert resp.status_code == 200
    assert [r["id"] for r in resp.json()] == ["mine"]


@pytest.mark.asyncio
async def test_list_runs_env_id_forbidden_without_access(api_app, monkeypatch):
    from bench.models import ActorType, EnvScope
    from bench_common.storage import django_store as store

    monkeypatch.setenv("BENCH_AUTH_DISABLED", "0")
    domain = _sample_domain("forbidden-env-domain")
    await store.save_domain(domain)
    env_id = "solo-env"
    await store.save_developer_environment(
        {
            "id": env_id,
            "owner_id": "1",
            "name": "Solo",
            "github_url": "https://github.com/org/solo",
            "status": "ready",
            "domain_id": domain.id,
            "scope": EnvScope.SOLO,
            "actor_type": ActorType.MEMBER,
            "actor_id": "1",
        }
    )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/v1/runs",
            params={"env_id": env_id},
            headers={"Authorization": f"Bearer {_member_token(user_id=99)}"},
        )
    assert resp.status_code == 403
