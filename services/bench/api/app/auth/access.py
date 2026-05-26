"""Resource access checks for runs and developer environments."""

from __future__ import annotations

import uuid

from bench.models import ActorType
from bench.models import DeveloperEnvironment as DevEnvRow
from bench.models import EnvScope
from bench.models import Run as RunRow
from fastapi import HTTPException

from app.auth.principal import Guest, Member, Principal
from app.auth.resolve import auth_disabled
from app.services import teams as team_svc


async def can_read_run(row: RunRow, principal: Principal) -> bool:
    if auth_disabled():
        return True
    if row.visibility == "gallery_public" and row.status == "completed":
        return True
    if isinstance(principal, Guest):
        return (
            row.actor_type == ActorType.GUEST and row.actor_id == principal.session_id
        )
    if isinstance(principal, Member):
        if row.actor_type == ActorType.MEMBER and row.actor_id == str(
            principal.user_id
        ):
            return True
        if row.team_id:
            return await team_svc.is_member(row.team_id, principal.user_id)
    return False


async def assert_run_read(run_id: str, principal: Principal) -> RunRow:
    try:
        row = await RunRow.objects.aget(id=run_id)
    except RunRow.DoesNotExist as exc:
        raise HTTPException(
            status_code=404, detail=f"Run '{run_id}' not found"
        ) from exc
    if not await can_read_run(row, principal):
        raise HTTPException(status_code=403, detail="Not allowed to view this run")
    return row


async def can_access_dev_env(row: DevEnvRow, principal: Principal) -> bool:
    if auth_disabled():
        return True
    if not isinstance(principal, Member):
        return False
    if row.scope == EnvScope.SOLO or not row.team_id:
        return row.actor_id == str(principal.user_id) or row.owner_id == str(
            principal.user_id
        )
    return await team_svc.is_member(row.team_id, principal.user_id)


async def assert_dev_env_access(env_id: str, principal: Principal) -> DevEnvRow:
    try:
        row = await DevEnvRow.objects.aget(id=env_id)
    except DevEnvRow.DoesNotExist as exc:
        raise HTTPException(
            status_code=404, detail=f"Environment '{env_id}' not found"
        ) from exc
    if not await can_access_dev_env(row, principal):
        raise HTTPException(
            status_code=403, detail="Not allowed to access this environment"
        )
    return row


async def domain_owner_member(domain_owner_id: str, member: Member) -> bool:
    return domain_owner_id == str(member.user_id)


def parse_team_id(team_id: str | None) -> uuid.UUID | None:
    if not team_id:
        return None
    try:
        return uuid.UUID(team_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid team_id") from exc
