"""Resolve developer environment for a new run."""

from __future__ import annotations

import uuid

from app.auth.access import assert_dev_env_access
from app.auth.principal import Guest, Member
from bench.models import EnvScope
from bench_common.storage import database as db
from fastapi import HTTPException


async def resolve_run_environment_id(
    *,
    env_id: str | None,
    domain_id: str,
    principal: Guest | Member,
    team_id: uuid.UUID | None,
) -> str | None:
    """
    Pick the developer environment row to attribute to a run.

    When ``env_id`` is omitted, auto-select if exactly one ready env matches
    domain + scope (solo actor or team). Multiple matches require an explicit id.
    """
    if env_id:
        await assert_dev_env_access(env_id, principal)
        env = await db.get_developer_environment(env_id)
        if env is None:
            raise HTTPException(status_code=404, detail=f"Environment '{env_id}' not found")
        if env.get("status") != "ready":
            raise HTTPException(
                status_code=400,
                detail=f"Environment is not ready (status: {env.get('status')})",
            )
        env_domain = env.get("domain_id")
        if env_domain and env_domain != domain_id:
            raise HTTPException(
                status_code=422,
                detail="env_id does not match run domain_id",
            )
        return env_id

    if isinstance(principal, Guest):
        return None

    candidates: list[dict] = []
    if team_id:
        candidates.extend(
            await db.list_developer_environments(
                scope=EnvScope.TEAM,
                team_id=str(team_id),
                domain_id=domain_id,
            )
        )
    candidates.extend(
        await db.list_developer_environments(
            scope=EnvScope.SOLO,
            actor_id=str(principal.user_id),
            domain_id=domain_id,
        )
    )
    seen: set[str] = set()
    unique: list[dict] = []
    for env in candidates:
        eid = env.get("id")
        if eid and eid not in seen:
            seen.add(eid)
            unique.append(env)

    ready = [e for e in unique if e.get("status") == "ready" and e.get("domain_id") == domain_id]
    if len(ready) == 1:
        return ready[0]["id"]
    if len(ready) > 1:
        raise HTTPException(
            status_code=422,
            detail=(
                "Multiple developer environments match this domain; "
                "pass env_id on POST /v1/runs"
            ),
        )
    return None
