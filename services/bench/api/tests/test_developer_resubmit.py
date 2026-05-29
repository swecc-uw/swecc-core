"""Resubmit updates the same bench_domain row instead of minting a new UUID."""

from __future__ import annotations

import pytest


def _sample_manifest(*, vow_version: str = "1.0.0") -> dict:
    return {
        "name": "Minesweeper",
        "description": "Test env",
        "binding_vow": {
            "id": "ignored-vow",
            "version": vow_version,
            "domain_id": "ignored",
            "tier": "tier1",
            "description": "test",
            "observation_space": {"type": "text", "description": "o"},
            "action_space": {"type": "text", "description": "a"},
            "reward": {"type": "scalar", "description": "r"},
            "episode": {
                "max_steps": 5,
                "supports_seed": True,
                "deterministic_reset": True,
            },
            "techniques": [],
        },
        "scoring": {
            "primary_metric": "score",
            "higher_is_better": True,
            "metrics": [
                {"name": "score", "type": "episode_reward", "aggregation": "mean"}
            ],
        },
    }


@pytest.fixture
def published_domain():
    from bench_common.core.binding_vow import BindingVow
    from bench_common.core.domain import Domain, EnvironmentEndpoint
    from bench_common.core.scoring import MetricDef, ScoringConfig

    domain_id = "resubmit-domain-test"
    vow = BindingVow(
        id=f"{domain_id}-vow",
        version="1.0.1",
        domain_id=domain_id,
        tier="tier1",
        description="test",
        observation_space={"type": "text", "description": "o"},
        action_space={"type": "text", "description": "a"},
        reward={"type": "scalar", "description": "r"},
        episode={"max_steps": 5, "supports_seed": True, "deterministic_reset": True},
        techniques=[],
    )
    return Domain(
        id=domain_id,
        name="Minesweeper",
        owner_id="42",
        binding_vow=vow,
        endpoint=EnvironmentEndpoint(
            mode="sandbox", url="http://bench-sandbox:8001/envs/old"
        ),
        scoring=ScoringConfig(
            primary_metric="score",
            higher_is_better=True,
            metrics=[
                MetricDef(name="score", type="episode_reward", aggregation="mean")
            ],
        ),
        status="published",
    )


@pytest.mark.asyncio
async def test_domain_from_manifest_reuses_id_and_updates_vow(
    django_db, published_domain
):
    from app.routes.developer import _domain_from_manifest
    from bench_common.storage import django_store as store

    await store.save_domain(published_domain)

    updated = await _domain_from_manifest(
        manifest=_sample_manifest(vow_version="1.0.2"),
        owner_id="42",
        env_id="env-abc",
        sandbox_base="http://bench-sandbox:8001",
        name="Minesweeper",
        description="Test env",
        reuse_domain_id=published_domain.id,
    )

    assert updated.id == published_domain.id
    assert updated.status == "published"
    assert updated.binding_vow.version == "1.0.2"
    assert updated.endpoint.url == "http://bench-sandbox:8001/envs/env-abc"
    assert any(v.version == "1.0.2" for v in updated.version_history)


@pytest.mark.asyncio
async def test_domain_from_manifest_creates_new_uuid_when_no_reuse(django_db):
    from app.routes.developer import _domain_from_manifest

    created = await _domain_from_manifest(
        manifest=_sample_manifest(vow_version="1.0.0"),
        owner_id="42",
        env_id="env-new",
        sandbox_base="http://bench-sandbox:8001",
        name="New Env",
        description="desc",
        reuse_domain_id=None,
    )

    assert created.id != "resubmit-domain-test"
    assert created.status == "draft"
    assert created.binding_vow.version == "1.0.0"
