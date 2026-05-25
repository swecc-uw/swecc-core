from __future__ import annotations

import uuid

from app.auth.access import parse_team_id
from app.auth.deps import get_optional_principal, require_member
from app.auth.policy import assert_can_manage_teams
from app.services import teams as team_svc
from bench.models import (
    ActorType,
    DeveloperEnvironment as DevEnvRow,
    EnvScope,
    MAX_TEAM_MEMBERS,
    Run as RunRow,
    Visibility,
)
from bench_common.core.domain import Domain
from bench_common.core.run import Run
from bench_common.storage.django_store import _model_from_row_data
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/teams", tags=["teams"])


class CreateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = None


class CreateTeamResponse(BaseModel):
    team_id: str
    name: str
    slug: str
    join_code: str
    member_count: int
    max_members: int
    role: str


class JoinTeamRequest(BaseModel):
    code: str = Field(min_length=4, max_length=4)


class TransferRequest(BaseModel):
    new_owner_user_id: int


class LeaderboardEntry(BaseModel):
    run_id: str
    model: str
    primary_score: float
    all_scores: dict[str, float]


@router.post("", response_model=CreateTeamResponse, status_code=201)
async def create_team(req: CreateTeamRequest, member=Depends(require_member)) -> CreateTeamResponse:
    team = await team_svc.create_team(
        name=req.name,
        owner_user_id=member.user_id,
        slug=req.slug,
    )
    return CreateTeamResponse(
        team_id=str(team.id),
        name=team.name,
        slug=team.slug,
        join_code=team.join_code,
        member_count=1,
        max_members=MAX_TEAM_MEMBERS,
        role="owner",
    )


@router.get("")
async def list_my_teams(member=Depends(require_member)) -> list[dict]:
    return await team_svc.list_teams_for_user(member.user_id)


@router.get("/{team_id}")
async def get_team(team_id: str, member=Depends(require_member)) -> dict:
    tid = parse_team_id(team_id)
    try:
        return await team_svc.get_team_detail(tid, viewer_user_id=member.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/{team_id}", status_code=204)
async def delete_team(team_id: str, member=Depends(require_member)) -> None:
    tid = parse_team_id(team_id)
    try:
        await team_svc.delete_team(tid, owner_user_id=member.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/join")
async def join_team(req: JoinTeamRequest, member=Depends(require_member)) -> dict:
    try:
        team = await team_svc.join_team_by_code(code=req.code, user_id=member.user_id)
    except ValueError as exc:
        msg = str(exc)
        status = 409 if "full" in msg.lower() else 404 if "Invalid" in msg else 422
        raise HTTPException(status_code=status, detail=msg) from exc
    count = await team_svc.member_count(team.id)
    return {
        "team_id": str(team.id),
        "name": team.name,
        "member_count": count,
        "max_members": MAX_TEAM_MEMBERS,
        "role": "member",
    }


@router.post("/{team_id}/join-code/regenerate")
async def regenerate_code(team_id: str, member=Depends(require_member)) -> dict:
    tid = parse_team_id(team_id)
    try:
        code = await team_svc.regenerate_join_code(tid, owner_user_id=member.user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"join_code": code}


@router.delete("/{team_id}/members/me")
async def leave_team(team_id: str, member=Depends(require_member)) -> dict:
    tid = parse_team_id(team_id)
    try:
        await team_svc.leave_team(tid, user_id=member.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"detail": "left"}


@router.delete("/{team_id}/members/{user_id}")
async def remove_member(team_id: str, user_id: int, member=Depends(require_member)) -> dict:
    tid = parse_team_id(team_id)
    try:
        await team_svc.remove_member(tid, owner_user_id=member.user_id, target_user_id=user_id)
    except (PermissionError, ValueError) as exc:
        status = 403 if isinstance(exc, PermissionError) else 404
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"detail": "removed"}


@router.post("/{team_id}/transfer")
async def transfer_ownership(
    team_id: str, req: TransferRequest, member=Depends(require_member)
) -> dict:
    tid = parse_team_id(team_id)
    try:
        await team_svc.transfer_ownership(
            tid,
            owner_user_id=member.user_id,
            new_owner_user_id=req.new_owner_user_id,
        )
    except (PermissionError, ValueError) as exc:
        status = 403 if isinstance(exc, PermissionError) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"detail": "transferred"}


@router.get("/{team_id}/runs", response_model=list[Run])
async def team_runs(team_id: str, member=Depends(require_member)) -> list[Run]:
    tid = parse_team_id(team_id)
    if not await team_svc.is_member(tid, member.user_id):
        raise HTTPException(status_code=403, detail="Not a member of this team")
    rows = RunRow.objects.filter(team_id=tid).order_by("-id")
    return [_model_from_row_data(Run, row.data) async for row in rows[:100]]


@router.get("/{team_id}/leaderboard", response_model=list[LeaderboardEntry])
async def team_leaderboard(team_id: str, member=Depends(require_member), limit: int = 50) -> list:
    tid = parse_team_id(team_id)
    if not await team_svc.is_member(tid, member.user_id):
        raise HTTPException(status_code=403, detail="Not a member of this team")
    rows = [
        row
        async for row in RunRow.objects.filter(team_id=tid, status="completed").order_by("-id")
    ]
    entries: list[LeaderboardEntry] = []
    for row in rows[:limit]:
        run = _model_from_row_data(Run, row.data)
        if not run.scores:
            continue
        primary = next(iter(run.scores.values()))
        entries.append(
            LeaderboardEntry(
                run_id=run.id,
                model=run.config.agent_config.model,
                primary_score=primary,
                all_scores=run.scores,
            )
        )
    entries.sort(key=lambda e: e.primary_score, reverse=True)
    return entries


@router.get("/{team_id}/environments")
async def team_environments(team_id: str, member=Depends(require_member)) -> list[dict]:
    tid = parse_team_id(team_id)
    if not await team_svc.is_member(tid, member.user_id):
        raise HTTPException(status_code=403, detail="Not a member of this team")
    from bench_common.storage import database as db

    return await db.list_developer_environments(scope=EnvScope.TEAM, team_id=str(tid))
