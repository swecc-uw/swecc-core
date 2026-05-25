"""
Bench API — developer test bench (1 model, 1 at a time) and full bench
(all 5 supported models, dispatched as a BenchJob for the EC2 worker or
run locally when no worker is configured).
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from app.auth.access import assert_dev_env_access
from app.auth.deps import require_member
from app.auth.worker import require_worker
from bench_common.config import settings
from bench_common.core.run import AgentConfig, Episode
from bench_common.orchestrator import service as orchestrator
from bench_common.storage import database as db
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

log = structlog.get_logger()

router = APIRouter(prefix="/v1/bench", tags=["bench"])

# Global lock — only one dev test bench at a time across the entire platform
_dev_bench_lock = asyncio.Lock()


# ── Dev Test Bench ─────────────────────────────────────────────────────────────


class TestBenchRequest(BaseModel):
    env_id: str
    model: str
    num_episodes: int = 1
    seed: int | None = None


@router.get("/status")
async def dev_bench_status() -> dict[str, bool]:
    """Returns whether a dev test bench is currently running."""
    return {"busy": _dev_bench_lock.locked()}


@router.post("/test", response_model=Episode)
async def test_bench(req: TestBenchRequest, member=Depends(require_member)) -> Episode:
    """Run a single dev test bench: one model, one episode at a time."""
    allowed_models = settings.supported_models + settings.accepted_model_aliases
    if req.model not in allowed_models:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported model {req.model!r}. Allowed: {allowed_models}",
        )

    if _dev_bench_lock.locked():
        raise HTTPException(
            status_code=429,
            detail="A dev test bench is already running. Only one at a time is supported.",
        )

    await assert_dev_env_access(req.env_id, member)
    env = await db.get_developer_environment(req.env_id)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{req.env_id}' not found")
    if env["status"] != "ready":
        raise HTTPException(
            status_code=400,
            detail=f"Environment is not ready (status: {env['status']}). "
            "Wait for onboarding to complete before benching.",
        )
    if not env.get("domain_id"):
        raise HTTPException(status_code=400, detail="Environment has no associated domain")

    domain = await db.get_domain(env["domain_id"])
    if domain is None:
        raise HTTPException(status_code=500, detail="Domain record not found")

    async with _dev_bench_lock:
        try:
            episode = await orchestrator.run_test_episode(
                domain_id=env["domain_id"],
                binding_vow_version=domain.binding_vow.version,
                agent_config=AgentConfig(model=req.model),
                env_url=env.get("env_url"),
                seed=req.seed,
                github_url=env.get("github_url"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    return episode


# ── Full Bench ─────────────────────────────────────────────────────────────────


class FullBenchResponse(BaseModel):
    id: str
    env_id: str
    domain_id: str | None
    status: str
    created_at: str


@router.post("/full/{env_id}", response_model=FullBenchResponse, status_code=202)
async def full_bench(
    env_id: str,
    member=Depends(require_member),
) -> dict[str, Any]:
    """Initiate a full bench: all 5 supported models against the env."""
    await assert_dev_env_access(env_id, member)
    env = await db.get_developer_environment(env_id)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{env_id}' not found")
    if env["status"] != "ready":
        raise HTTPException(
            status_code=400,
            detail=f"Environment is not ready (status: {env['status']})",
        )

    job = await db.create_bench_job(
        env_id=env_id,
        domain_id=env.get("domain_id"),
        github_url=env["github_url"],
    )

    # Run locally in background (EC2 worker will claim queued jobs in production)
    asyncio.create_task(_run_full_bench_local(job["id"]))

    return job


async def _run_full_bench_local(job_id: str) -> None:
    """Local full-bench runner — iterates all 5 models sequentially."""
    job = await db.get_bench_job(job_id)
    if job is None:
        return

    claimed = await db.claim_bench_job(job_id)
    if claimed is None:
        return

    domain_id = job.get("domain_id")
    if not domain_id:
        await db.complete_bench_job(job_id, {}, failed=True)
        return

    domain = await db.get_domain(domain_id)
    if domain is None:
        await db.complete_bench_job(job_id, {}, failed=True)
        return

    env = None
    envs = await db.list_developer_environments()
    for e in envs:
        if e.get("domain_id") == domain_id:
            env = e
            break

    model_results: dict[str, Any] = {}
    episodes_per_model = settings.full_bench_episodes_per_model

    for model in settings.supported_models:
        log.info("full_bench_model_start", job_id=job_id, model=model)
        try:
            from bench_common.core.run import RunConfig

            run_config = RunConfig(
                domain_id=domain_id,
                binding_vow_version=domain.binding_vow.version,
                agent_config=AgentConfig(model=model),
                num_episodes=episodes_per_model,
            )
            run = await orchestrator.create_run(run_config, requester_id="full_bench")
            # Wait for the run to complete (it runs as background tasks)
            for _ in range(120):
                await asyncio.sleep(2.0)
                run = await db.get_run(run.id)
                if run and run.status in ("completed", "failed"):
                    break

            primary_score = (
                run.scores.get(domain.scoring.primary_metric) if run and run.scores else None
            )
            model_results[model] = {
                "run_id": run.id if run else None,
                "status": run.status if run else "failed",
                "primary_score": primary_score,
            }
            log.info("full_bench_model_done", job_id=job_id, model=model, score=primary_score)
        except Exception as exc:
            log.exception("full_bench_model_failed", job_id=job_id, model=model, error=str(exc))
            model_results[model] = {"run_id": None, "status": "failed", "primary_score": None}

    await db.complete_bench_job(job_id, model_results)
    log.info("full_bench_complete", job_id=job_id)


# ── Job management (EC2 worker interface) ──────────────────────────────────────


class CompleteJobRequest(BaseModel):
    model_results: dict[str, Any]
    failed: bool = False


@router.get("/jobs", dependencies=[Depends(require_worker)])
async def list_bench_jobs(
    env_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    return await db.list_bench_jobs(env_id=env_id, status=status)


@router.get("/jobs/{job_id}", dependencies=[Depends(require_worker)])
async def get_bench_job(job_id: str) -> dict[str, Any]:
    job = await db.get_bench_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Bench job '{job_id}' not found")
    return job


@router.patch("/jobs/{job_id}/claim")
async def claim_bench_job(job_id: str) -> dict[str, Any]:
    job = await db.claim_bench_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' cannot be claimed (not found or not queued)",
        )
    return job


@router.patch("/jobs/{job_id}/complete", dependencies=[Depends(require_worker)])
async def complete_bench_job(job_id: str, req: CompleteJobRequest) -> dict[str, Any]:
    job = await db.complete_bench_job(job_id, req.model_results, failed=req.failed)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Bench job '{job_id}' not found")
    return job
