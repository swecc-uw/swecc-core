"""
Leaderboard routes.
Builds rankings dynamically from completed Run records in Postgres.
"""

from bench_common.storage import database as db
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.schemas import DEFAULT_LEADERBOARD_LIMIT, MAX_LEADERBOARD_LIMIT

router = APIRouter(prefix="/v1/leaderboards", tags=["leaderboard"])


class LeaderboardEntry(BaseModel):
    run_id: str
    model: str
    binding_vow_version: str
    num_episodes: int
    primary_score: float
    all_scores: dict[str, float]


class LeaderboardsBatchResponse(BaseModel):
    leaderboards: dict[str, list[LeaderboardEntry]]


def _entries_from_rows(rows, primary: str) -> list[LeaderboardEntry]:
    entries: list[LeaderboardEntry] = []
    for item in rows:
        run = item.run
        entries.append(
            LeaderboardEntry(
                run_id=run.id,
                model=run.config.agent_config.model,
                binding_vow_version=run.config.binding_vow_version,
                num_episodes=item.num_episodes,
                primary_score=run.scores.get(primary, 0.0),
                all_scores=run.scores,
            )
        )
    return entries


@router.get("", response_model=LeaderboardsBatchResponse)
async def get_leaderboards_batch(
    domain_ids: str = Query(..., description="Comma-separated domain ids"),
    limit: int = Query(
        DEFAULT_LEADERBOARD_LIMIT,
        ge=1,
        le=MAX_LEADERBOARD_LIMIT,
        description=f"Entries per domain (max {MAX_LEADERBOARD_LIMIT})",
    ),
) -> LeaderboardsBatchResponse:
    """Batch leaderboard fetch for home gallery (one request for many domain cards)."""
    ids = [d.strip() for d in domain_ids.split(",") if d.strip()]
    if not ids:
        raise HTTPException(status_code=422, detail="domain_ids is required")
    if len(ids) > 50:
        raise HTTPException(status_code=422, detail="At most 50 domain_ids per request")

    leaderboards: dict[str, list[LeaderboardEntry]] = {}
    for domain_id in ids:
        domain = await db.get_domain(domain_id)
        if domain is None or domain.status != "published":
            leaderboards[domain_id] = []
            continue
        primary = domain.scoring.primary_metric
        rows = await db.list_leaderboard_runs(
            domain_id,
            primary_metric=primary,
            higher_is_better=domain.scoring.higher_is_better,
            limit=limit,
        )
        leaderboards[domain_id] = _entries_from_rows(rows, primary)
    return LeaderboardsBatchResponse(leaderboards=leaderboards)


@router.get("/{domain_id}", response_model=list[LeaderboardEntry])
async def get_leaderboard(
    domain_id: str,
    limit: int = Query(
        DEFAULT_LEADERBOARD_LIMIT,
        ge=1,
        le=MAX_LEADERBOARD_LIMIT,
        description=f"Max entries (default {DEFAULT_LEADERBOARD_LIMIT}, max {MAX_LEADERBOARD_LIMIT})",
    ),
) -> list[LeaderboardEntry]:
    return await _leaderboard_for_domain(domain_id, limit=limit)


async def _leaderboard_for_domain(domain_id: str, *, limit: int) -> list[LeaderboardEntry]:
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    if domain.status != "published":
        return []

    primary = domain.scoring.primary_metric
    rows = await db.list_leaderboard_runs(
        domain_id,
        primary_metric=primary,
        higher_is_better=domain.scoring.higher_is_better,
        limit=limit,
    )
    return _entries_from_rows(rows, primary)
