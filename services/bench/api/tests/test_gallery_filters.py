"""Gallery listing excludes archived/unpublished domains and demoted runs."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


def _sample_domain(domain_id: str = "gallery-test-domain"):
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
        name="Gallery Test",
        owner_id="owner-1",
        binding_vow=vow,
        endpoint=EnvironmentEndpoint(mode="remote", url="http://127.0.0.1:1"),
        scoring=ScoringConfig(
            primary_metric="score",
            higher_is_better=True,
            metrics=[MetricDef(name="score", type="episode_reward", aggregation="mean")],
        ),
        status="published",
    )


def _sample_run(domain_id: str, run_id: str = "gallery-test-run"):
    from bench_common.core.run import AgentConfig, Run, RunConfig

    return Run(
        id=run_id,
        config=RunConfig(
            domain_id=domain_id,
            binding_vow_version="1.0.0",
            agent_config=AgentConfig(model="test/model"),
        ),
        requester_id="owner-1",
        status="completed",
        scores={"score": 1.0},
    )


@pytest.mark.asyncio
async def test_list_gallery_runs_excludes_unpublished_domain(django_db):
    from bench.models import ActorType
    from bench_common.storage import django_store as store

    domain = _sample_domain()
    run = _sample_run(domain.id)
    await store.save_domain(domain)
    await store.save_run(
        run,
        actor_type=ActorType.GUEST,
        actor_id="guest-1",
        visibility="gallery_public",
    )

    visible = await store.list_gallery_runs()
    assert len(visible) == 1

    await store.save_domain(domain.model_copy(update={"status": "archived"}))
    assert await store.list_gallery_runs() == []


@pytest.mark.asyncio
async def test_archive_domain_gallery_demotes_public_runs(django_db):
    from bench.models import ActorType
    from bench.models import Run as RunRow
    from bench.models import Visibility
    from bench_common.storage import django_store as store

    domain = _sample_domain("archive-domain")
    run = _sample_run(domain.id, run_id="archive-run")
    await store.save_domain(domain)
    await store.save_run(
        run,
        actor_type=ActorType.GUEST,
        actor_id="guest-1",
        visibility="gallery_public",
    )

    await store.archive_domain_gallery(domain.id)

    assert await store.list_gallery_runs() == []
    row = await RunRow.objects.aget(id=run.id)
    assert row.visibility == Visibility.PRIVATE


@pytest.mark.asyncio
async def test_list_domains_excludes_archived_by_default(django_db):
    from bench_common.storage import django_store as store

    active = _sample_domain("active-domain")
    archived = _sample_domain("archived-domain")
    await store.save_domain(active)
    await store.save_domain(archived.model_copy(update={"status": "archived"}))

    listed = await store.list_domains()
    listed_ids = {d.id for d in listed}
    assert active.id in listed_ids
    assert archived.id not in listed_ids

    with_archived = await store.list_domains(include_archived=True)
    assert archived.id in {d.id for d in with_archived}


@pytest.mark.asyncio
async def test_gallery_runs_pagination(django_db, api_app):
    from bench.models import ActorType, Visibility
    from bench_common.storage import django_store as store

    domain = _sample_domain("gallery-page-domain")
    await store.save_domain(domain)
    for i in range(6):
        await store.save_run(
            _sample_run(domain.id, f"gallery-run-{i}"),
            actor_type=ActorType.GUEST,
            actor_id=f"g{i}",
            visibility=Visibility.GALLERY_PUBLIC,
        )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        page1 = await client.get("/v1/gallery/runs", params={"domain_id": domain.id, "limit": 5})
        assert page1.status_code == 200
        body1 = page1.json()
        assert len(body1["items"]) == 5
        assert body1["next_cursor"] is not None

        page2 = await client.get(
            "/v1/gallery/runs",
            params={
                "domain_id": domain.id,
                "limit": 5,
                "cursor": body1["next_cursor"],
            },
        )
        assert page2.status_code == 200
        body2 = page2.json()
        assert len(body2["items"]) == 1
        assert body2["next_cursor"] is None

        page1_ids = {item["run_id"] for item in body1["items"]}
        page2_ids = {item["run_id"] for item in body2["items"]}
        assert page1_ids.isdisjoint(page2_ids)
