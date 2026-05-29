"""Helpers for run list endpoints (pagination + episode summaries)."""

from __future__ import annotations

from datetime import datetime

from app.schemas import RunListItem
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


async def runs_to_list_items(runs: list[Run], *, include_episode_summary: bool) -> list[RunListItem]:
    if not runs:
        return []
    summaries = {}
    if include_episode_summary:
        summaries = await db.episode_summaries_for_runs([r.id for r in runs])
    out: list[RunListItem] = []
    for run in runs:
        summary = summaries.get(run.id)
        out.append(
            RunListItem(
                **run.model_dump(),
                completed_count=summary.completed_count if summary else 0,
                failed_count=summary.failed_count if summary else 0,
                avg_reward=summary.avg_reward if summary else None,
            )
        )
    return out
