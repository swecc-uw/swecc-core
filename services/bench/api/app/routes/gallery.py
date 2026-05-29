from __future__ import annotations

from app.auth.deps import get_optional_principal
from app.auth.principal import Guest, Member
from app.auth.resolve import auth_disabled
from app.schemas import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    DomainActivityItem,
    DomainActivityResponse,
)
from app.services.run_list import runs_to_list_items
from bench_common.core.run import Run
from bench_common.storage import database as db
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from bench.models import ActorType

router = APIRouter(prefix="/v1/gallery", tags=["gallery"])


class GalleryRunEntry(BaseModel):
    run_id: str
    domain_id: str
    model: str
    primary_score: float | None
    created_at: str
    actor_label: str = "Guest"


@router.get("/runs", response_model=list[GalleryRunEntry])
async def list_gallery_runs(
    domain_id: str | None = None,
    limit: int = 50,
) -> list[GalleryRunEntry]:
    domain = None
    if domain_id:
        domain = await db.get_domain(domain_id)
        if domain is None:
            raise HTTPException(
                status_code=404, detail=f"Domain '{domain_id}' not found"
            )

    entries: list[GalleryRunEntry] = []
    primary_key = domain.scoring.primary_metric if domain else None
    higher = domain.scoring.higher_is_better if domain else True

    for run, row in await db.list_gallery_runs(
        domain_id=domain_id, limit=min(limit, 100)
    ):
        scores = run.scores or {}
        primary = None
        if primary_key and primary_key in scores:
            primary = scores[primary_key]
        elif scores:
            primary = next(iter(scores.values()))
        entries.append(
            GalleryRunEntry(
                run_id=run.id,
                domain_id=run.config.domain_id,
                model=run.config.agent_config.model,
                primary_score=primary,
                created_at=run.created_at.isoformat(),
                actor_label="Guest" if row.actor_type == ActorType.GUEST else "Member",
            )
        )

    if primary_key:
        missing_sentinel = float("-inf") if higher else float("inf")
        entries.sort(
            key=lambda e: (
                e.primary_score if e.primary_score is not None else missing_sentinel
            ),
            reverse=higher,
        )
    return entries


def _merge_activity(
    mine: list[DomainActivityItem],
    gallery: list[DomainActivityItem],
    *,
    limit: int,
) -> list[DomainActivityItem]:
    seen: set[str] = set()
    merged: list[DomainActivityItem] = []
    for item in sorted(
        mine + gallery,
        key=lambda x: x.created_at,
        reverse=True,
    ):
        if item.id in seen:
            continue
        seen.add(item.id)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


@router.get("/domains/{domain_id}/activity", response_model=DomainActivityResponse)
async def domain_activity_feed(
    domain_id: str,
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    mine_limit: int | None = Query(None, ge=1, le=MAX_LIST_LIMIT),
    gallery_limit: int | None = Query(None, ge=1, le=MAX_LIST_LIMIT),
    principal=Depends(get_optional_principal),
) -> DomainActivityResponse:
    """
    Merged recent runs for a domain: the caller's runs plus public gallery runs.

    Replaces separate GET /v1/me/runs and GET /v1/gallery/runs calls on domain pages.
    """
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    m_cap = mine_limit if mine_limit is not None else max(1, limit // 2)
    g_cap = gallery_limit if gallery_limit is not None else max(1, limit - m_cap)

    mine_runs: list[Run] = []
    if auth_disabled() and isinstance(principal, Member):
        mine_runs = await db.list_runs(
            domain_id=domain_id,
            actor_type=ActorType.MEMBER,
            actor_id=str(principal.user_id),
            limit=m_cap,
        )
    elif isinstance(principal, Guest):
        mine_runs = await db.list_runs(
            domain_id=domain_id,
            actor_type=ActorType.GUEST,
            actor_id=principal.session_id,
            limit=m_cap,
        )
    elif isinstance(principal, Member):
        mine_runs = await db.list_runs(
            domain_id=domain_id,
            actor_type=ActorType.MEMBER,
            actor_id=str(principal.user_id),
            limit=m_cap,
        )

    gallery_pairs = await db.list_gallery_runs(domain_id=domain_id, limit=g_cap)
    gallery_runs = [r for r, _ in gallery_pairs]

    mine_items = [
        DomainActivityItem(**item.model_dump(), source="mine")
        for item in await runs_to_list_items(mine_runs, include_episode_summary=True)
    ]
    gallery_items = [
        DomainActivityItem(**item.model_dump(), source="gallery")
        for item in await runs_to_list_items(gallery_runs, include_episode_summary=True)
    ]

    items = _merge_activity(mine_items, gallery_items, limit=limit)
    next_cursor = items[-1].id if len(items) >= limit else None
    return DomainActivityResponse(items=items, next_cursor=next_cursor)
