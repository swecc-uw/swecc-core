"""Authorization capability checks for bench-api."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import structlog
from app.auth.principal import Anonymous, Guest, Member, Principal
from app.auth.resolve import auth_disabled
from bench_common.config import settings
from fastapi import HTTPException

log = structlog.get_logger()


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


def _run_submission_cooldown_key(actor_key: str) -> str:
    return f"bench:run_submit_cooldown:{actor_key}"


async def assert_run_submission_cooldown(actor_key: str) -> None:
    """Enforce a minimum gap between run submissions for one caller identity."""
    if auth_disabled():
        return

    seconds = settings.run_submission_cooldown_seconds
    if seconds <= 0:
        return

    key = _run_submission_cooldown_key(actor_key)
    try:
        from app.redis_client import get_redis

        client = get_redis()
        acquired = await client.set(key, "1", nx=True, ex=seconds)
        if acquired:
            return
        ttl = await client.ttl(key)
    except Exception as exc:
        log.warning("run_submission_cooldown_redis_unavailable", error=str(exc))
        return

    retry_after = max(1, int(ttl)) if ttl and ttl > 0 else seconds
    raise HTTPException(
        status_code=429,
        detail=(
            f"Please wait {retry_after} seconds before starting another bench run. "
            "This cooldown protects shared inference capacity."
        ),
        headers={"Retry-After": str(retry_after)},
    )


async def assert_guest_rate_limit(guest_session_id: str) -> None:
    from bench.models import ActorType
    from bench.models import Run as RunRow

    limit = settings.guest_runs_per_day
    if limit <= 0:
        return

    # Count only runs created today (UTC).  RunRow has no native created_at
    # column so we query the JSON data field.  ISO-8601 strings are
    # lexicographically ordered identically to chronological order, so __gte
    # on the ISO prefix of today's midnight is correct and index-friendly on
    # Postgres jsonb.
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
    count = await RunRow.objects.filter(
        actor_type=ActorType.GUEST,
        actor_id=guest_session_id,
        data__created_at__gte=today_iso,
    ).acount()
    if count >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Guest run limit reached ({limit} runs per day). Sign in to continue.",
        )
