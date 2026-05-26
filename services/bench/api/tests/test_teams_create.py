"""Integration test: team create service against migrated bench schema."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def django_db():
    """File-backed sqlite so async ORM threadpool shares the same schema."""
    fd, db_path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.django_settings")
    os.environ.setdefault("DB_HOST", "localhost")
    os.environ.setdefault("DB_NAME", "test")
    os.environ.setdefault("DB_PORT", "5432")
    os.environ.setdefault("DB_USER", "test")
    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

    import django
    from django.conf import settings

    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": db_path,
    }
    django.setup()

    from django.core.management import call_command

    call_command("migrate", "bench", verbosity=0)

    yield db_path

    Path(db_path).unlink(missing_ok=True)


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
    from bench.models import BenchTeam

    from app.services import teams as team_svc

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
