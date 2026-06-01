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


@pytest.mark.asyncio
async def test_episode_summaries_for_runs_batched(django_db):
    from bench.models import ActorType
    from bench_common.core.run import Episode
    from bench_common.storage import django_store as store

    domain = _sample_domain("summary-batch-domain")
    await store.save_domain(domain)
    run_a = _sample_run(domain.id, "summary-run-a")
    run_b = _sample_run(domain.id, "summary-run-b")
    await store.save_run(
        run_a,
        actor_type=ActorType.GUEST,
        actor_id="g1",
        visibility="gallery_public",
    )
    await store.save_run(
        run_b,
        actor_type=ActorType.GUEST,
        actor_id="g2",
        visibility="gallery_public",
    )
    await store.save_episode(
        Episode(
            id="ep-a1",
            run_id=run_a.id,
            status="failed",
            terminal_info={"reason": "episode_error", "error": "boom"},
        )
    )
    await store.save_episode(
        Episode(
            id="ep-b1",
            run_id=run_b.id,
            status="truncated",
            terminal_info={"reason": "step_limit"},
        )
    )

    summaries = await store.episode_summaries_for_runs([run_a.id, run_b.id])
    assert summaries[run_a.id].failed_count == 1
    assert summaries[run_a.id].failure_reasons == ("episode_error",)
    assert summaries[run_b.id].truncated_count == 1
    assert summaries[run_b.id].truncation_reasons == ("step_limit",)


@pytest.mark.asyncio
async def test_gallery_activity_pagination(django_db, api_app, monkeypatch):
    from datetime import datetime, timedelta

    from bench.models import ActorType, Visibility
    from bench_common.storage import django_store as store

    monkeypatch.setenv("BENCH_AUTH_DISABLED", "1")
    domain = _sample_domain("activity-page-domain")
    await store.save_domain(domain)
    base = datetime(2026, 1, 1, 12, 0, 0)
    for i in range(6):
        run = _sample_run(domain.id, f"activity-run-{i}").model_copy(
            update={"created_at": base + timedelta(minutes=i)}
        )
        await store.save_run(
            run,
            actor_type=ActorType.MEMBER if i % 2 == 0 else ActorType.GUEST,
            actor_id="0" if i % 2 == 0 else f"g{i}",
            visibility=Visibility.GALLERY_PUBLIC if i % 2 else Visibility.PRIVATE,
        )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        page1 = await client.get(
            f"/v1/gallery/domains/{domain.id}/activity",
            params={"limit": 5},
        )
        assert page1.status_code == 200
        body1 = page1.json()
        assert len(body1["items"]) == 5
        assert body1["next_cursor"] is not None

        page2 = await client.get(
            f"/v1/gallery/domains/{domain.id}/activity",
            params={"limit": 5, "cursor": body1["next_cursor"]},
        )
        assert page2.status_code == 200
        body2 = page2.json()
        assert len(body2["items"]) == 1
        assert body2["next_cursor"] is None

        page1_ids = {item["id"] for item in body1["items"]}
        page2_ids = {item["id"] for item in body2["items"]}
        assert page1_ids.isdisjoint(page2_ids)
        assert page1_ids | page2_ids == {f"activity-run-{i}" for i in range(6)}
