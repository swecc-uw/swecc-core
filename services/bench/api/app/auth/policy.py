"""Authorization capability checks for bench-api."""

from __future__ import annotations

import os

from app.auth.principal import Anonymous, Guest, Member, Principal
from app.auth.resolve import auth_disabled
from bench_common.config import settings
from fastapi import HTTPException


def assert_can_manage_teams(principal: Principal) -> Member:
    if auth_disabled():
        return Member(user_id=0, username="local", groups=("is_authenticated",))
    if not isinstance(principal, Member):
        raise HTTPException(status_code=403, detail="SWECC member account required for teams")
    return principal


def assert_can_submit_dev_env(principal: Principal) -> Member:
    return assert_can_manage_teams(principal)


def assert_guest_can_create_run(domain_id: str) -> None:
    allowlist = settings.demo_domain_ids
    if not allowlist:
        return
    if domain_id not in allowlist:
        raise HTTPException(
            status_code=403,
            detail=f"Guests may only run demo domains: {', '.join(allowlist)}",
        )


async def assert_guest_rate_limit(guest_session_id: str) -> None:
    from bench.models import ActorType
    from bench.models import Run as RunRow

    limit = settings.guest_runs_per_day
    if limit <= 0:
        return
    count = await RunRow.objects.filter(
        actor_type=ActorType.GUEST,
        actor_id=guest_session_id,
    ).acount()
    if count >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Guest run limit reached ({limit} runs). Sign in to continue.",
        )
