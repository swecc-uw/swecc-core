"""
Keep Domain rows and developer_environment rows aligned.

Gallery lists published domains; developer lists developer_environment rows.
Upload paths (GitHub onboarding, POST /v1/domains, CLI register) must publish
and mirror so both surfaces stay in sync.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bench_common.core.domain import Domain
from bench_common.storage import django_store as store
from django.db.models import Q

from bench.models import DeveloperEnvironment as DeveloperEnvironmentRow


async def publish_domain_if_needed(domain: Domain) -> Domain:
    if domain.status == "published":
        return domain
    published = domain.model_copy(update={"status": "published"})
    await store.save_domain(published)
    return published


async def mirror_developer_env_from_domain(
    domain: Domain,
    *,
    env_row_id: str | None = None,
    github_url: str | None = None,
) -> None:
    """Upsert a developer_environment row linked to this domain."""
    env_url = domain.endpoint.url if domain.endpoint else None
    defaults: dict[str, Any] = {
        "owner_id": domain.owner_id,
        "name": domain.name,
        "description": domain.detail,
        "status": "ready",
        "domain_id": domain.id,
        "env_url": env_url,
        "error_message": None,
    }
    if github_url is not None:
        defaults["github_url"] = github_url

    if env_row_id:
        row = await DeveloperEnvironmentRow.objects.filter(id=env_row_id).afirst()
        if row is None:
            defaults["github_url"] = github_url if github_url is not None else ""
            await DeveloperEnvironmentRow.objects.acreate(id=env_row_id, **defaults)
            return
        for key, value in defaults.items():
            setattr(row, key, value)
        await row.asave()
        return

    row = await DeveloperEnvironmentRow.objects.filter(
        Q(id=domain.id) | Q(domain_id=domain.id)
    ).afirst()
    if row is not None:
        for key, value in defaults.items():
            setattr(row, key, value)
        if github_url is not None:
            row.github_url = github_url
        await row.asave()
        return

    await DeveloperEnvironmentRow.objects.acreate(
        id=domain.id,
        github_url=github_url if github_url is not None else "",
        created_at=datetime.utcnow(),
        **defaults,
    )


async def ensure_gallery_visible(
    domain: Domain,
    *,
    env_row_id: str | None = None,
    github_url: str | None = None,
) -> Domain:
    """Publish the domain and mirror metadata to developer environments."""
    published = await publish_domain_if_needed(domain)
    await mirror_developer_env_from_domain(
        published,
        env_row_id=env_row_id,
        github_url=github_url,
    )
    return published
