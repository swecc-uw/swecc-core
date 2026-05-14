from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from bench_common.core.run import AgentConfig, Episode
from bench_common.orchestrator import service as orchestrator
from bench_common.storage import database as db
from bench_common.storage.trace_store import trace_store

router = APIRouter(prefix="/v1/test", tags=["test"])


class TestEpisodeRequest(BaseModel):
    domain_id: str
    binding_vow_version: str
    agent_config: AgentConfig
    env_url: str | None = None
    seed: int | None = None


@router.post("/episode", response_model=Episode, status_code=200)
async def start_test_episode(req: TestEpisodeRequest) -> Episode:
    try:
        episode = await orchestrator.run_test_episode(
            domain_id=req.domain_id,
            binding_vow_version=req.binding_vow_version,
            agent_config=req.agent_config,
            env_url=req.env_url,
            seed=req.seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return episode


@router.get("/episode/{episode_id}", response_model=Episode)
async def get_episode(episode_id: str) -> Episode:
    episode = await db.get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail=f"Episode '{episode_id}' not found")
    return episode


@router.get("/episode/{episode_id}/trace")
async def get_episode_trace(episode_id: str) -> list:
    episode = await db.get_episode(episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail=f"Episode '{episode_id}' not found")
    events = await trace_store.read(episode_id)
    return [e.model_dump() for e in events]
