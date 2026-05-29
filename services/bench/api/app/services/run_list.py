"""Helpers for run list endpoints (pagination + episode summaries)."""

from __future__ import annotations

from datetime import datetime

from app.schemas import RunListItem
from app.services.actor_usernames import member_usernames_by_id
from bench.models import ActorType
from bench.models import Run as RunRow
from bench_common.core.run import Run
from bench_common.storage import database as db
from fastapi import HTTPException


def parse_created_before(value: str | None) -> datetime | None:
    if not value:
        return None
    from django.utils.dateparse import parse_datetime

    parsed = parse_datetime(value)
    if parsed is None:
        raise HTTPException(
            status_code=422,
            detail="created_before must be an ISO-8601 datetime",
        )
    return parsed


async def _run_row_meta_by_id(
    run_ids: list[str],
) -> dict[str, tuple[str | None, str | None, str | None]]:
    if not run_ids:
        return {}
    out: dict[str, tuple[str | None, str | None, str | None]] = {}
    async for rid, actor_type, actor_id, visibility in RunRow.objects.filter(
        id__in=run_ids
    ).values_list("id", "actor_type", "actor_id", "visibility"):
        out[rid] = (actor_type, actor_id, visibility)
    return out


def _resolve_actor_username(
    *,
    actor_type: str | None,
    actor_id: str | None,
    member_names: dict[str, str],
) -> str | None:
    if not actor_type:
        return None
    if actor_type == ActorType.GUEST:
        return "Guest"
    if actor_type == ActorType.MEMBER and actor_id:
        return member_names.get(actor_id)
    return None


async def runs_to_list_items(
    runs: list[Run], *, include_episode_summary: bool
) -> list[RunListItem]:
    if not runs:
        return []
    run_ids = [r.id for r in runs]
    summaries = {}
    if include_episode_summary:
        summaries = await db.episode_summaries_for_runs(run_ids)
    row_meta = await _run_row_meta_by_id(run_ids)
    member_ids: list[int] = []
    for actor_type, actor_id, _visibility in row_meta.values():
        if actor_type == ActorType.MEMBER and actor_id:
            try:
                member_ids.append(int(actor_id))
            except ValueError:
                pass
    member_names = await member_usernames_by_id(member_ids)
    out: list[RunListItem] = []
    for run in runs:
        summary = summaries.get(run.id)
        actor_type, actor_id, visibility = row_meta.get(run.id, (None, None, None))
        out.append(
            RunListItem(
                **run.model_dump(),
                completed_count=summary.completed_count if summary else 0,
                failed_count=summary.failed_count if summary else 0,
                avg_reward=summary.avg_reward if summary else None,
                actor_type=actor_type,
                actor_id=actor_id,
                actor_username=_resolve_actor_username(
                    actor_type=actor_type,
                    actor_id=actor_id,
                    member_names=member_names,
                ),
                visibility=visibility,
            )
        )
    return out
