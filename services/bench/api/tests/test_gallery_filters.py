"""Gallery listing excludes archived/unpublished domains and demoted runs."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


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
