"""Domain-scoped run list helpers (mine vs gallery surfaces)."""

from __future__ import annotations

from datetime import datetime

from app.auth.principal import Anonymous, Guest, Member, Principal
from bench.models import ActorType
from bench_common.core.run import Run
from bench_common.storage import database as db
from bench_common.storage.django_store import ActivityRun


def _principal_actor(principal: Principal) -> tuple[str | None, str | None]:
    if isinstance(principal, Guest):
        return ActorType.GUEST, principal.session_id
    if isinstance(principal, Member):
        return ActorType.MEMBER, str(principal.user_id)
    return None, None


async def list_mine_runs_for_domain(
    domain_id: str,
    principal: Principal,
    *,
    limit: int,
    cursor: str | None = None,
    created_before: datetime | None = None,
) -> list[Run]:
    """Runs owned by the caller on a domain (member, guest, or local dev member)."""
    if isinstance(principal, Guest):
        return await db.list_runs(
            domain_id=domain_id,
            actor_type=ActorType.GUEST,
            actor_id=principal.session_id,
            limit=limit,
            cursor=cursor,
            created_before=created_before,
        )
    if isinstance(principal, Member):
        return await db.list_runs(
            domain_id=domain_id,
            actor_type=ActorType.MEMBER,
            actor_id=str(principal.user_id),
            limit=limit,
            cursor=cursor,
            created_before=created_before,
        )
    return []


async def list_gallery_runs_for_domain(
    domain_id: str,
    *,
    limit: int,
    cursor: str | None = None,
) -> list[Run]:
    pairs = await db.list_gallery_runs(domain_id=domain_id, limit=limit, cursor=cursor)
    return [run for run, _ in pairs]


async def list_domain_activity_runs_for_domain(
    domain_id: str,
    principal: Principal,
    *,
    limit: int,
    cursor: str | None = None,
) -> list[ActivityRun]:
    """Merged recent runs for a domain page (mine + public gallery) in one query."""
    if isinstance(principal, Anonymous):
        actor_type, actor_id = None, None
    else:
        actor_type, actor_id = _principal_actor(principal)
    return await db.list_domain_activity_runs(
        domain_id,
        actor_type=actor_type,
        actor_id=actor_id,
        limit=limit,
        cursor=cursor,
    )
