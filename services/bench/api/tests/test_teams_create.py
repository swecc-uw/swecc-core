"""Integration test: team create service against migrated bench schema."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_team_persists_owner_membership(django_db):
    from app.services import teams as team_svc

    team = await team_svc.create_team(name="hello", owner_user_id=42)
    assert team.name == "hello"
    assert team.slug == "hello"
    assert len(team.join_code) == 4
    assert await team_svc.is_member(team.id, 42)
    assert await team_svc.member_count(team.id) == 1


@pytest.mark.asyncio
async def test_delete_team_owner_removes_team(django_db):
    from app.services import teams as team_svc

    from bench.models import BenchTeam

    team = await team_svc.create_team(name="delete-me", owner_user_id=42)
    await team_svc.delete_team(team.id, owner_user_id=42)
    assert not await BenchTeam.objects.filter(id=team.id).aexists()


@pytest.mark.asyncio
async def test_delete_team_non_owner_forbidden(django_db):
    from app.services import teams as team_svc

    team = await team_svc.create_team(name="protected", owner_user_id=42)
    with pytest.raises(PermissionError, match="Only the team owner"):
        await team_svc.delete_team(team.id, owner_user_id=99)
    assert await team_svc.is_member(team.id, 42)
