from __future__ import annotations

from app.auth.deps import get_optional_principal
from app.schemas import (
    DEFAULT_GALLERY_LIMIT,
    MAX_LIST_LIMIT,
    DomainActivityItem,
    DomainActivityResponse,
    GalleryRunEntry,
    GalleryRunsResponse,
)
from app.services.domain_runs import list_domain_activity_runs_for_domain
from app.services.run_list import runs_to_list_items
from bench.models import ActorType
from bench_common.core.domain import Domain
from bench_common.core.run import Run
from bench_common.storage import database as db
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter(prefix="/v1/gallery", tags=["gallery"])


def _gallery_run_entry(
    run: Run,
    *,
    row_actor_type: str,
    domain: Domain | None,
) -> GalleryRunEntry:
    primary_key = domain.scoring.primary_metric if domain else None
    scores = run.scores or {}
    primary = None
    if primary_key and primary_key in scores:
        primary = scores[primary_key]
    elif scores:
        primary = next(iter(scores.values()))
    return GalleryRunEntry(
        run_id=run.id,
        domain_id=run.config.domain_id,
        model=run.config.agent_config.model,
        primary_score=primary,
        created_at=run.created_at.isoformat(),
        actor_label="Guest" if row_actor_type == ActorType.GUEST else "Member",
    )


def _next_cursor(items: list[GalleryRunEntry], *, limit: int) -> str | None:
    if len(items) < limit:
        return None
    return items[-1].run_id


@router.get("/runs", response_model=GalleryRunsResponse)
async def list_gallery_runs(
    domain_id: str | None = None,
    limit: int = Query(
        DEFAULT_GALLERY_LIMIT,
        ge=1,
        le=MAX_LIST_LIMIT,
        description=f"Max runs per page (default {DEFAULT_GALLERY_LIMIT}, max {MAX_LIST_LIMIT})",
    ),
    cursor: str | None = Query(
        None,
        description="Pagination cursor: run_id of the last item from the previous page",
    ),
) -> GalleryRunsResponse:
    domain = None
    if domain_id:
        domain = await db.get_domain(domain_id)
        if domain is None:
            raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    pairs = await db.list_gallery_runs(domain_id=domain_id, limit=limit, cursor=cursor)
    entries = [
        _gallery_run_entry(run, row_actor_type=row.actor_type, domain=domain) for run, row in pairs
    ]
    return GalleryRunsResponse(items=entries, next_cursor=_next_cursor(entries, limit=limit))


@router.get("/domains/{domain_id}/activity", response_model=DomainActivityResponse)
async def domain_activity_feed(
    domain_id: str,
    limit: int = Query(DEFAULT_GALLERY_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    cursor: str | None = Query(
        None,
        description="Pagination cursor: run id of the last item from the previous page",
    ),
    principal=Depends(get_optional_principal),
) -> DomainActivityResponse:
    """
    Merged recent runs for a domain: the caller's runs plus public gallery runs.

    Replaces separate GET /v1/me/runs and GET /v1/gallery/runs calls on domain pages.
    """
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    activity_rows = await list_domain_activity_runs_for_domain(
        domain_id,
        principal,
        limit=limit,
        cursor=cursor,
    )
    sources = {row.run.id: row.source for row in activity_rows}
    list_items = await runs_to_list_items(
        [row.run for row in activity_rows],
        include_episode_summary=True,
    )
    items = [
        DomainActivityItem(**item.model_dump(), source=sources[item.id]) for item in list_items
    ]
    next_cursor = items[-1].id if len(items) >= limit else None
    return DomainActivityResponse(items=items, next_cursor=next_cursor)
