from __future__ import annotations

from bench.models import ActorType, EnvScope
from bench_common.core.run import Run
from bench_common.storage import database as db
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth.deps import get_optional_principal, get_principal, require_member
from app.auth.principal import Anonymous, Guest, Member
from app.services import teams as team_svc

router = APIRouter(prefix="/v1/me", tags=["me"])


class MeResponse(BaseModel):
    type: str
    user_id: int | None = None
    username: str | None = None
    guest_session_id: str | None = None


class MeContextResponse(BaseModel):
    solo: dict
    teams: list[dict]


@router.get("", response_model=MeResponse)
async def me(principal=Depends(get_optional_principal)) -> MeResponse:
    if isinstance(principal, Member):
        return MeResponse(
            type="member",
            user_id=principal.user_id,
            username=principal.username,
        )
    if isinstance(principal, Guest):
        return MeResponse(type="guest", guest_session_id=principal.session_id)
    return MeResponse(type="anonymous")


@router.get("/context", response_model=MeContextResponse)
async def me_context(member: Member = Depends(require_member)) -> MeContextResponse:
    solo_envs = await db.count_dev_envs(
        actor_id=str(member.user_id), scope=EnvScope.SOLO
    )
    solo_runs = await db.list_runs(
        actor_type=ActorType.MEMBER,
        actor_id=str(member.user_id),
        limit=1000,
    )
    enriched = []
    for t in await team_svc.list_teams_for_user(member.user_id):
        envs = await db.list_developer_environments(
            scope=EnvScope.TEAM, team_id=t["team_id"]
        )
        enriched.append({**t, "env_count": len(envs)})
    return MeContextResponse(
        solo={"env_count": solo_envs, "run_count": len(solo_runs)},
        teams=enriched,
    )


@router.get("/runs", response_model=list[Run])
async def my_runs(
    team_id: str | None = Query(None),
    principal=Depends(get_principal),
) -> list[Run]:
    if isinstance(principal, Guest):
        return await db.list_runs(
            actor_type=ActorType.GUEST,
            actor_id=principal.session_id,
            team_id=team_id,
        )
    return await db.list_runs(
        actor_type=ActorType.MEMBER,
        actor_id=str(principal.user_id),
        team_id=team_id,
    )
