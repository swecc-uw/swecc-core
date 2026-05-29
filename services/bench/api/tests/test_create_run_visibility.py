"""POST /v1/runs visibility defaults for members."""

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


def _sample_domain(domain_id: str = "visibility-domain"):
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
        name="Visibility Test",
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


def _create_body(*, visibility: str | None = None) -> dict:
    body = {
        "domain_id": "visibility-domain",
        "binding_vow_version": "1.0.0",
        "agent_config": {"model": "test/model"},
        "num_episodes": 1,
    }
    if visibility is not None:
        body["visibility"] = visibility
    return body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("visibility", "expected"),
    [
        (None, "gallery_public"),
        ("gallery_public", "gallery_public"),
        ("private", "private"),
        ("invalid", "gallery_public"),
    ],
)
async def test_create_run_member_visibility(
    api_app, monkeypatch, visibility: str | None, expected: str
):
    from bench_common.core.run import AgentConfig, Run, RunConfig
    from bench_common.storage import django_store as store

    from bench.models import Run as RunRow
    from bench.models import Visibility

    monkeypatch.setenv("BENCH_AUTH_DISABLED", "0")

    async def noop_cooldown(_actor_key: str) -> None:
        return

    async def fake_create_run(config: RunConfig, *, requester_id: str) -> Run:
        return Run(
            id="member-run-1",
            config=config,
            requester_id=requester_id,
            status="pending",
        )

    monkeypatch.setattr("app.routes.runs.assert_run_submission_cooldown", noop_cooldown)
    monkeypatch.setattr("app.routes.runs.orchestrator.create_run", fake_create_run)

    domain = _sample_domain()
    await store.save_domain(domain)

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/runs",
            headers={"Authorization": f"Bearer {_member_token(user_id=1)}"},
            json=_create_body(visibility=visibility),
        )

    assert resp.status_code == 202, resp.text
    row = await RunRow.objects.aget(id="member-run-1")
    assert row.visibility == getattr(Visibility, expected.upper())
