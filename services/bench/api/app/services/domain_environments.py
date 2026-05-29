"""List developer environments for a domain (member-visible solo + team rows)."""

from __future__ import annotations

from typing import Any

from app.auth.principal import Member
from app.services import teams as team_svc
from bench_common.storage import database as db

from bench.models import EnvScope


async def list_environments_for_domain_member(
    domain_id: str,
    member: Member,
) -> list[dict[str, Any]]:
    """Environments the member can see for one domain (solo + team scopes, deduped)."""
    solo = await db.list_developer_environments(
        scope=EnvScope.SOLO,
        actor_id=str(member.user_id),
        domain_id=domain_id,
    )
    teams = await team_svc.list_teams_for_user(member.user_id)
    team_envs: list[dict[str, Any]] = []
    from app.auth.access import parse_team_id

    for t in teams:
        tid = parse_team_id(t["team_id"])
        if tid:
            team_envs.extend(
                await db.list_developer_environments(
                    scope=EnvScope.TEAM,
                    team_id=str(tid),
                    domain_id=domain_id,
                )
            )
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for env in solo + team_envs:
        eid = env.get("id")
        if eid and eid not in seen:
            seen.add(eid)
            out.append(env)
    return out
