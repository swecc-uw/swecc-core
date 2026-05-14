from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from bench_common.core.run import Episode, Run, RunConfig
from bench_common.orchestrator import service as orchestrator
from bench_common.storage import database as db
from bench_common.storage.trace_store import trace_store

router = APIRouter(prefix="/v1/runs", tags=["runs"])


@router.get("", response_model=list[Run])
async def list_runs(domain_id: str | None = None) -> list[Run]:
    return await db.list_runs(domain_id=domain_id)


@router.post("", response_model=Run, status_code=202)
async def create_run(config: RunConfig) -> Run:
    try:
        run = await orchestrator.create_run(config, requester_id="local")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return run


@router.get("/{run_id}", response_model=Run)
async def get_run(run_id: str) -> Run:
    run = await db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run


@router.get("/{run_id}/episodes", response_model=list[Episode])
async def list_episodes(run_id: str) -> list[Episode]:
    run = await db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return await db.get_episodes(run_id)


@router.get("/{run_id}/traces")
async def get_traces(run_id: str) -> dict:
    run = await db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    episodes = await db.get_episodes(run_id)
    result = {}
    for ep in episodes:
        events = await trace_store.read(ep.id)
        result[ep.id] = [e.model_dump() for e in events]
    return result
