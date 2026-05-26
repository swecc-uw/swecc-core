from __future__ import annotations

from bench.models import ActorType
from bench_common.storage import database as db
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
            raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    entries: list[GalleryRunEntry] = []
    primary_key = domain.scoring.primary_metric if domain else None
    higher = domain.scoring.higher_is_better if domain else True

    for run, row in await db.list_gallery_runs(domain_id=domain_id, limit=min(limit, 100)):
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
            key=lambda e: (e.primary_score if e.primary_score is not None else missing_sentinel),
            reverse=higher,
        )
    return entries
