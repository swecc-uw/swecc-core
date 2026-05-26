from __future__ import annotations

import re
import uuid

from django.db import IntegrityError

from bench.models import (
    MAX_TEAM_MEMBERS,
    BenchTeam,
    BenchTeamMembership,
    TeamRole,
    generate_join_code,
)


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "team"
    return base


async def _unique_join_code() -> str:
    for _ in range(32):
        code = generate_join_code()
        if not await BenchTeam.objects.filter(join_code=code).aexists():
            return code
    raise RuntimeError("Could not allocate unique join code")


async def _unique_slug(name: str) -> str:
    base = _slugify(name)
    slug = base
    n = 0
    while await BenchTeam.objects.filter(slug=slug).aexists():
        n += 1
        slug = f"{base}-{n}"
    return slug


async def member_count(team_id: uuid.UUID) -> int:
    return await BenchTeamMembership.objects.filter(team_id=team_id).acount()


async def is_member(team_id: uuid.UUID, user_id: int) -> bool:
    return await BenchTeamMembership.objects.filter(team_id=team_id, user_id=user_id).aexists()


async def create_team(*, name: str, owner_user_id: int, slug: str | None = None) -> BenchTeam:
    resolved_slug = slug or await _unique_slug(name)
    if slug and await BenchTeam.objects.filter(slug=resolved_slug).aexists():
        raise ValueError("Team slug already exists")

    for _ in range(8):
        try:
            team = await BenchTeam.objects.acreate(
                id=uuid.uuid4(),
                name=name,
                slug=resolved_slug,
                join_code=await _unique_join_code(),
                created_by_user_id=owner_user_id,
            )
            break
        except IntegrityError:
            continue
    else:
        raise RuntimeError("Could not create team with unique join code")
    await BenchTeamMembership.objects.acreate(
        team=team,
        user_id=owner_user_id,
        role=TeamRole.OWNER,
    )
    return team


async def join_team_by_code(*, code: str, user_id: int) -> BenchTeam:
    normalized = code.strip().upper()
    if len(normalized) != 4:
        raise ValueError("Join code must be 4 characters")
    team = await BenchTeam.objects.filter(join_code=normalized).afirst()
    if team is None:
        raise ValueError("Invalid join code")
    if await is_member(team.id, user_id):
        return team
    count = await member_count(team.id)
    if count >= MAX_TEAM_MEMBERS:
        raise ValueError("Team is full (maximum 4 members)")
    await BenchTeamMembership.objects.acreate(
        team=team,
        user_id=user_id,
        role=TeamRole.MEMBER,
    )
    return team


async def regenerate_join_code(team_id: uuid.UUID, *, owner_user_id: int) -> str:
    team = await BenchTeam.objects.aget(id=team_id)
    membership = await BenchTeamMembership.objects.filter(
        team_id=team_id, user_id=owner_user_id, role=TeamRole.OWNER
    ).afirst()
    if membership is None:
        raise PermissionError("Only the team owner can regenerate the join code")
    code = await _unique_join_code()
    team.join_code = code
    await team.asave(update_fields=["join_code"])
    return code


async def list_teams_for_user(user_id: int) -> list[dict]:
    memberships = BenchTeamMembership.objects.filter(user_id=user_id).select_related("team")
    out = []
    async for m in memberships:
        count = await member_count(m.team_id)
        out.append(
            {
                "team_id": str(m.team_id),
                "name": m.team.name,
                "slug": m.team.slug,
                "role": m.role,
                "member_count": count,
                "max_members": MAX_TEAM_MEMBERS,
                "join_code": m.team.join_code if m.role == TeamRole.OWNER else None,
            }
        )
    return out


async def get_team_detail(team_id: uuid.UUID, *, viewer_user_id: int) -> dict:
    if not await is_member(team_id, viewer_user_id):
        raise PermissionError("Not a member of this team")
    team = await BenchTeam.objects.aget(id=team_id)
    membership = await BenchTeamMembership.objects.filter(
        team_id=team_id, user_id=viewer_user_id
    ).afirst()
    count = await member_count(team_id)
    return {
        "team_id": str(team.id),
        "name": team.name,
        "slug": team.slug,
        "role": membership.role if membership else None,
        "member_count": count,
        "max_members": MAX_TEAM_MEMBERS,
        "join_code": (team.join_code if membership and membership.role == TeamRole.OWNER else None),
    }


async def delete_team(team_id: uuid.UUID, *, owner_user_id: int) -> None:
    membership = await BenchTeamMembership.objects.filter(
        team_id=team_id, user_id=owner_user_id, role=TeamRole.OWNER
    ).afirst()
    if membership is None:
        raise PermissionError("Only the team owner can delete the team")
    await BenchTeam.objects.filter(id=team_id).adelete()


async def leave_team(team_id: uuid.UUID, *, user_id: int) -> None:
    membership = await BenchTeamMembership.objects.filter(team_id=team_id, user_id=user_id).afirst()
    if membership is None:
        raise ValueError("Not a member of this team")
    if membership.role == TeamRole.OWNER:
        raise ValueError("Owner must transfer ownership or delete the team before leaving")
    await membership.adelete()


async def remove_member(team_id: uuid.UUID, *, owner_user_id: int, target_user_id: int) -> None:
    owner = await BenchTeamMembership.objects.filter(
        team_id=team_id, user_id=owner_user_id, role=TeamRole.OWNER
    ).afirst()
    if owner is None:
        raise PermissionError("Only the team owner can remove members")
    if owner_user_id == target_user_id:
        raise ValueError("Owner cannot remove themselves; delete team or transfer ownership")
    deleted, _ = await BenchTeamMembership.objects.filter(
        team_id=team_id, user_id=target_user_id
    ).adelete()
    if not deleted:
        raise ValueError("User is not on this team")


async def transfer_ownership(
    team_id: uuid.UUID, *, owner_user_id: int, new_owner_user_id: int
) -> None:
    owner = await BenchTeamMembership.objects.filter(
        team_id=team_id, user_id=owner_user_id, role=TeamRole.OWNER
    ).afirst()
    if owner is None:
        raise PermissionError("Only the team owner can transfer ownership")
    new_owner = await BenchTeamMembership.objects.filter(
        team_id=team_id, user_id=new_owner_user_id
    ).afirst()
    if new_owner is None:
        raise ValueError("New owner must already be a team member")
    owner.role = TeamRole.MEMBER
    new_owner.role = TeamRole.OWNER
    await owner.asave(update_fields=["role"])
    await new_owner.asave(update_fields=["role"])
    team = await BenchTeam.objects.aget(id=team_id)
    team.created_by_user_id = new_owner_user_id
    await team.asave(update_fields=["created_by_user_id"])
