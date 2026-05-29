"""API fixes: pagination, slim domains, leaderboard limit, activity feed."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


def _sample_domain(domain_id: str = "api-fixes-domain"):
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
        name="API Fixes",
        owner_id="owner-1",
        binding_vow=vow,
        endpoint=EnvironmentEndpoint(mode="remote", url="http://127.0.0.1:1"),
        scoring=ScoringConfig(
            primary_metric="score",
            higher_is_better=True,
            metrics=[MetricDef(name="score", type="episode_reward", aggregation="mean")],
        ),
        status="published",
        tags=["tag-a"],
        image_url="https://example.com/img.png",
    )


def _sample_run(domain_id: str, run_id: str, *, status: str = "completed"):
    from bench_common.core.run import AgentConfig, Run, RunConfig

    return Run(
        id=run_id,
        config=RunConfig(
            domain_id=domain_id,
            binding_vow_version="1.0.0",
            agent_config=AgentConfig(model="test/model"),
        ),
        requester_id="owner-1",
        status=status,
        scores={"score": 1.0},
    )


@pytest.mark.asyncio
async def test_list_runs_honors_limit_in_db(django_db, api_app, monkeypatch):
    from bench_common.storage import django_store as store

    from bench.models import ActorType

    monkeypatch.setenv("BENCH_AUTH_DISABLED", "1")
    domain = _sample_domain()
    await store.save_domain(domain)
    for i in range(5):
        await store.save_run(
            _sample_run(domain.id, f"run-{i}"),
            actor_type=ActorType.MEMBER,
            actor_id="1",
        )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/runs", params={"domain_id": domain.id, "limit": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert "completed_count" in body[0]


@pytest.mark.asyncio
async def test_list_domains_slim_by_default(django_db, api_app):
    from bench_common.storage import django_store as store

    domain = _sample_domain("slim-domain")
    await store.save_domain(domain)

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/domains")
    assert resp.status_code == 200
    row = next(d for d in resp.json() if d["id"] == domain.id)
    assert set(row.keys()) == {"id", "name", "tags", "image"}
    assert row["image"] == domain.image_url


@pytest.mark.asyncio
async def test_leaderboard_respects_limit(django_db, api_app):
    from bench_common.storage import django_store as store

    from bench.models import ActorType, Visibility

    domain = _sample_domain("lb-limit-domain")
    await store.save_domain(domain)
    for i in range(5):
        await store.save_run(
            _sample_run(domain.id, f"lb-run-{i}", status="completed").model_copy(
                update={"scores": {"score": float(i)}}
            ),
            actor_type=ActorType.GUEST,
            actor_id="g1",
            visibility=Visibility.GALLERY_PUBLIC,
        )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/v1/leaderboards/{domain.id}", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_leaderboard_batch(django_db, api_app):
    from bench_common.storage import django_store as store

    from bench.models import ActorType, Visibility

    d1 = _sample_domain("batch-d1")
    d2 = _sample_domain("batch-d2")
    await store.save_domain(d1)
    await store.save_domain(d2)
    for domain, rid in ((d1, "b1"), (d2, "b2")):
        await store.save_run(
            _sample_run(domain.id, rid),
            actor_type=ActorType.GUEST,
            actor_id="g1",
            visibility=Visibility.GALLERY_PUBLIC,
        )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/v1/leaderboards",
            params={"domain_ids": f"{d1.id},{d2.id}", "limit": 5},
        )
    assert resp.status_code == 200
    data = resp.json()["leaderboards"]
    assert d1.id in data and d2.id in data
    assert len(data[d1.id]) == 1


@pytest.mark.asyncio
async def test_gallery_activity_feed_merges(django_db, api_app, monkeypatch):
    from bench_common.storage import django_store as store

    from bench.models import ActorType, Visibility

    monkeypatch.setenv("BENCH_AUTH_DISABLED", "1")
    domain = _sample_domain("activity-domain")
    await store.save_domain(domain)
    await store.save_run(
        _sample_run(domain.id, "mine-run"),
        actor_type=ActorType.MEMBER,
        actor_id="0",
        visibility="private",
    )
    await store.save_run(
        _sample_run(domain.id, "gallery-run"),
        actor_type=ActorType.GUEST,
        actor_id="g1",
        visibility=Visibility.GALLERY_PUBLIC,
    )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/v1/gallery/domains/{domain.id}/activity", params={"limit": 10})
    assert resp.status_code == 200
    items = resp.json()["items"]
    sources = {i["source"] for i in items}
    assert "mine" in sources
    assert "gallery" in sources


@pytest.mark.asyncio
async def test_domain_runs_mine_and_gallery(django_db, api_app, monkeypatch):
    from bench_common.storage import django_store as store

    from bench.models import ActorType, Visibility

    monkeypatch.setenv("BENCH_AUTH_DISABLED", "1")
    domain = _sample_domain("split-runs-domain")
    await store.save_domain(domain)
    await store.save_run(
        _sample_run(domain.id, "mine-only"),
        actor_type=ActorType.MEMBER,
        actor_id="0",
        visibility="private",
    )
    await store.save_run(
        _sample_run(domain.id, "gallery-only"),
        actor_type=ActorType.GUEST,
        actor_id="g1",
        visibility=Visibility.GALLERY_PUBLIC,
    )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        mine = await client.get(f"/v1/domains/{domain.id}/runs/mine")
        gallery = await client.get(f"/v1/domains/{domain.id}/runs/gallery")
    assert mine.status_code == 200
    assert gallery.status_code == 200
    mine_ids = {r["id"] for r in mine.json()}
    gallery_ids = {r["id"] for r in gallery.json()}
    assert "mine-only" in mine_ids
    assert "gallery-only" in gallery_ids
    assert "gallery-only" not in mine_ids


@pytest.mark.asyncio
async def test_batch_run_status_respects_access(django_db, api_app, monkeypatch):
    from bench_common.storage import django_store as store

    from bench.models import ActorType, Visibility

    monkeypatch.setenv("BENCH_AUTH_DISABLED", "1")
    domain = _sample_domain("status-batch-domain")
    await store.save_domain(domain)
    await store.save_run(
        _sample_run(domain.id, "readable-run", status="running"),
        actor_type=ActorType.MEMBER,
        actor_id="0",
        visibility="private",
    )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/v1/runs/status", params={"ids": "readable-run,unknown"})
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert "readable-run" in runs
    assert runs["readable-run"]["status"] == "running"
    assert "unknown" not in runs
