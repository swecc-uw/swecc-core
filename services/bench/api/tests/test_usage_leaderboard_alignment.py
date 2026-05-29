"""Usage stats and leaderboard align with gallery eligibility criteria."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def _sample_domain(domain_id: str = "usage-alignment-domain", *, status: str = "published"):
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
        name="Usage Alignment Test",
        owner_id="owner-1",
        binding_vow=vow,
        endpoint=EnvironmentEndpoint(mode="remote", url="http://127.0.0.1:1"),
        scoring=ScoringConfig(
            primary_metric="score",
            higher_is_better=True,
            metrics=[MetricDef(name="score", type="episode_reward", aggregation="mean")],
        ),
        status=status,
    )


def _sample_run(
    domain_id: str,
    run_id: str,
    *,
    status: str = "completed",
    scores: dict[str, float] | None = None,
):
    from bench_common.core.run import AgentConfig, Run, RunConfig

    return Run(
        id=run_id,
        config=RunConfig(
            domain_id=domain_id,
            binding_vow_version="1.0.0",
            agent_config=AgentConfig(model="test/model"),
            num_episodes=2,
        ),
        requester_id="owner-1",
        status=status,
        scores=scores,
    )


@pytest.mark.asyncio
async def test_get_domain_usage_stats_breakdown(django_db):
    from bench.models import ActorType
    from bench_common.storage import django_store as store

    domain = _sample_domain()
    await store.save_domain(domain)

    runs = [
        (
            _sample_run(domain.id, "private-completed", scores={"score": 10.0}),
            "private",
        ),
        (
            _sample_run(domain.id, "public-completed", scores={"score": 8.0}),
            "gallery_public",
        ),
        (
            _sample_run(domain.id, "public-failed", status="failed", scores={}),
            "gallery_public",
        ),
        (_sample_run(domain.id, "public-no-scores", scores={}), "gallery_public"),
        (
            _sample_run(domain.id, "public-high", scores={"score": 12.0}),
            "gallery_public",
        ),
    ]
    for run, visibility in runs:
        await store.save_run(
            run,
            actor_type=ActorType.GUEST,
            actor_id="guest-1",
            visibility=visibility,
        )

    stats = await store.get_domain_usage_stats(domain.id)

    assert stats["total_runs"] == 5
    assert stats["total_episodes"] == 10
    assert stats["by_status"] == {"completed": 4, "failed": 1}
    assert stats["gallery_eligible"] == 3
    assert stats["leaderboard_eligible"] == 2
    assert stats["leaderboard_entries"] == 2
    assert stats["avg_score"] == 10.0
    assert stats["best_score"] == 12.0


@pytest.mark.asyncio
async def test_get_domain_usage_stats_unpublished_domain_excludes_gallery(django_db):
    from bench.models import ActorType
    from bench_common.storage import django_store as store

    domain = _sample_domain(status="draft")
    run = _sample_run(domain.id, "draft-public", scores={"score": 5.0})
    await store.save_domain(domain)
    await store.save_run(
        run,
        actor_type=ActorType.GUEST,
        actor_id="guest-1",
        visibility="gallery_public",
    )

    stats = await store.get_domain_usage_stats(domain.id)

    assert stats["total_runs"] == 1
    assert stats["gallery_eligible"] == 0
    assert stats["leaderboard_eligible"] == 0
    assert stats["avg_score"] is None
    assert stats["best_score"] is None


@pytest.mark.asyncio
async def test_get_domain_usage_stats_does_not_query_leaderboard_table(django_db):
    from bench.models import ActorType
    from bench_common.storage import django_store as store

    domain = _sample_domain()
    run = _sample_run(domain.id, "scored-run", scores={"score": 7.0})
    await store.save_domain(domain)
    await store.save_run(
        run,
        actor_type=ActorType.GUEST,
        actor_id="guest-1",
        visibility="gallery_public",
    )

    with patch(
        "bench_common.storage.django_store.LeaderboardRow.objects.filter",
        new=AsyncMock(side_effect=AssertionError("Leaderboard table must not be queried")),
    ):
        stats = await store.get_domain_usage_stats(domain.id)

    assert stats["leaderboard_eligible"] == 1
    assert stats["avg_score"] == 7.0


@pytest.mark.asyncio
async def test_leaderboard_excludes_unpublished_domain(api_app, django_db):
    from bench.models import ActorType
    from bench_common.storage import django_store as store

    domain = _sample_domain("leaderboard-draft-domain", status="draft")
    run = _sample_run(domain.id, "leaderboard-draft-run", scores={"score": 9.0})
    await store.save_domain(domain)
    await store.save_run(
        run,
        actor_type=ActorType.GUEST,
        actor_id="guest-1",
        visibility="gallery_public",
    )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/v1/leaderboards/{domain.id}")

    assert resp.status_code == 200
    assert resp.json() == []
