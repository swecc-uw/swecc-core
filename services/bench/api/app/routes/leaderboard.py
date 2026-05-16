"""
Leaderboard routes.
Builds rankings dynamically from completed Run records in SQLite.
"""

from bench_common.storage import database as db
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/leaderboards", tags=["leaderboard"])


class LeaderboardEntry(BaseModel):
    run_id: str
    model: str
    binding_vow_version: str
    num_episodes: int
    primary_score: float
    all_scores: dict[str, float]


@router.get("/{domain_id}", response_model=list[LeaderboardEntry])
async def get_leaderboard(domain_id: str, limit: int = 50) -> list[LeaderboardEntry]:
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    runs = await db.list_runs(domain_id=domain_id)
    completed = [r for r in runs if r.status == "completed" and r.scores]

    primary = domain.scoring.primary_metric
    higher = domain.scoring.higher_is_better

    completed.sort(
        key=lambda r: r.scores.get(primary, float("-inf")),
        reverse=higher,
    )

    entries: list[LeaderboardEntry] = []
    for run in completed[:limit]:
        episodes = await db.get_episodes(run.id)
        entries.append(
            LeaderboardEntry(
                run_id=run.id,
                model=run.config.agent_config.model,
                binding_vow_version=run.config.binding_vow_version,
                num_episodes=len(episodes),
                primary_score=run.scores.get(primary, 0.0),
                all_scores=run.scores,
            )
        )

    return entries
