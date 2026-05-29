from __future__ import annotations

from app.auth.deps import get_optional_principal, get_principal, require_member
from app.auth.principal import Guest, Member
from app.schemas import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT, MeWithContextResponse, RunListItem
from app.services import teams as team_svc
from app.services.run_list import parse_created_before, runs_to_list_items
from bench.models import ActorType, EnvScope
from bench.models import Run as RunRow
from bench_common.storage import database as db
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

router = APIRouter(prefix="/v1/me", tags=["me"])


class MeResponse(BaseModel):
    type: str
    user_id: int | None = None
    username: str | None = None
    guest_session_id: str | None = None


class MeContextResponse(BaseModel):
    solo: dict
    teams: list[dict]


async def _build_me_context(member: Member) -> MeContextResponse:
    solo_envs = await db.count_dev_envs(actor_id=str(member.user_id), scope=EnvScope.SOLO)
    solo_run_count = await RunRow.objects.filter(
        actor_type=ActorType.MEMBER,
        actor_id=str(member.user_id),
        team_id__isnull=True,
    ).acount()
    enriched = []
    for t in await team_svc.list_teams_for_user(member.user_id):
        team_id = t["team_id"]
        envs = await db.list_developer_environments(scope=EnvScope.TEAM, team_id=team_id)
        team_run_count = await RunRow.objects.filter(team_id=team_id).acount()
        enriched.append({**t, "env_count": len(envs), "run_count": team_run_count})
    return MeContextResponse(
        solo={"env_count": solo_envs, "run_count": solo_run_count},
        teams=enriched,
    )


@router.get("")
async def me(
    include: str | None = Query(
        None,
        description="Optional expansions, e.g. include=context for dashboard counts",
    ),
    principal=Depends(get_optional_principal),
) -> MeResponse | MeWithContextResponse:
    """Idempotent identity probe; safe to call on every page load."""
    if isinstance(principal, Member):
        base = MeResponse(
            type="member",
            user_id=principal.user_id,
            username=principal.username,
        )
        if include == "context":
            ctx = await _build_me_context(principal)
            return MeWithContextResponse(
                **base.model_dump(),
                context=ctx.model_dump(),
            )
        return base
    if isinstance(principal, Guest):
        return MeResponse(type="guest", guest_session_id=principal.session_id)
    return MeResponse(type="anonymous")


@router.get("/context", response_model=MeContextResponse)
async def me_context(member: Member = Depends(require_member)) -> MeContextResponse:
    return await _build_me_context(member)


@router.get("/runs", response_model=list[RunListItem])
async def my_runs(
    domain_id: str | None = Query(None, description="Filter to a single domain"),
    team_id: str | None = Query(None),
    limit: int = Query(
        DEFAULT_LIST_LIMIT,
        ge=1,
        le=MAX_LIST_LIMIT,
        description=f"Max runs (default {DEFAULT_LIST_LIMIT}, max {MAX_LIST_LIMIT})",
    ),
    cursor: str | None = Query(None, description="Id of the last run from the previous page"),
    created_before: str | None = Query(None, description="ISO-8601 created_before filter"),
    principal=Depends(get_principal),
) -> list[RunListItem]:
    created = parse_created_before(created_before)
    if isinstance(principal, Guest):
        runs = await db.list_runs(
            domain_id=domain_id,
            actor_type=ActorType.GUEST,
            actor_id=principal.session_id,
            team_id=team_id,
            limit=limit,
            cursor=cursor,
            created_before=created,
        )
    else:
        runs = await db.list_runs(
            domain_id=domain_id,
            actor_type=ActorType.MEMBER,
            actor_id=str(principal.user_id),
            team_id=team_id,
            limit=limit,
            cursor=cursor,
            created_before=created,
        )
    return await runs_to_list_items(runs, include_episode_summary=True)
