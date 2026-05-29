"""Domain-scoped run list helpers (mine vs gallery surfaces)."""

from __future__ import annotations

from datetime import datetime

from app.auth.principal import Guest, Member, Principal
from bench_common.core.run import Run
from bench_common.storage import database as db

from bench.models import ActorType


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


async def list_gallery_runs_for_domain(domain_id: str, *, limit: int) -> list[Run]:
    pairs = await db.list_gallery_runs(domain_id=domain_id, limit=limit)
    return [run for run, _ in pairs]
