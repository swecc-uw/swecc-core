"""
Platform status endpoint — counts, in-flight task visibility, recent failures.

Lets operators answer "what is the platform doing right now?" without
shelling into Postgres. Member-gated; the data isn't strictly sensitive
but anonymous viewers don't need it.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from app.auth.deps import require_member
from bench_common.config import settings as bench_settings
from bench_common.orchestrator import service as orchestrator
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bench.models import BenchJob as BenchJobRow
from bench.models import DeveloperEnvironment as DevEnvRow
from bench.models import Episode as EpisodeRow
from bench.models import Run as RunRow

log = structlog.get_logger()

router = APIRouter(prefix="/v1/admin", tags=["admin"])


class CountsByStatus(BaseModel):
    runs: dict[str, int]
    episodes: dict[str, int]
    developer_envs: dict[str, int]
    bench_jobs: dict[str, int]


class InFlight(BaseModel):
    active_run_tasks: int
    active_episode_tasks: int
    sandbox_port_pool_in_use: int | None = None
    sandbox_port_pool_total: int | None = None
    sandbox_reachable: bool = False


class PlatformStatus(BaseModel):
    counts: CountsByStatus
    in_flight: InFlight
    recent_failures: list[dict[str, Any]]
    reaper_enabled: bool


async def _counts(model_cls) -> dict[str, int]:
    """Return {status: count} for any of the bench models."""
    out: dict[str, int] = {}
    qs = model_cls.objects.values_list("status", flat=True)
    async for status in qs:
        out[status] = out.get(status, 0) + 1
    return out


async def _sandbox_pool_usage() -> tuple[int | None, int | None, bool]:
    """Ask bench-sandbox how many of its subprocess ports are taken."""
    base = bench_settings.sandbox_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{base}/admin/ports")
            if resp.status_code != 200:
                return None, None, True  # reachable but no admin endpoint
            data = resp.json()
            return data.get("in_use"), data.get("total"), True
    except (httpx.TransportError, httpx.HTTPError, ValueError):
        return None, None, False


async def _recent_failures(limit: int = 10) -> list[dict[str, Any]]:
    """Most recent failed runs — useful for spotting fresh outages."""
    out: list[dict[str, Any]] = []
    qs = RunRow.objects.filter(status__in=["failed", "cancelled"]).order_by("-id")[
        :limit
    ]
    async for row in qs:
        out.append(
            {
                "run_id": row.id,
                "domain_id": row.domain_id,
                "status": row.status,
                "actor_type": row.actor_type,
            }
        )
    return out


@router.get("/status", response_model=PlatformStatus)
async def platform_status(_: Any = Depends(require_member)) -> PlatformStatus:
    """One-shot snapshot of what bench-api is doing.

    Cheap by design — a handful of `COUNT(*)` queries plus a probe call to
    bench-sandbox.  Safe to poll every few seconds from an ops dashboard.
    """
    run_counts = await _counts(RunRow)
    ep_counts = await _counts(EpisodeRow)
    env_counts = await _counts(DevEnvRow)
    job_counts = await _counts(BenchJobRow)
    sb_in_use, sb_total, sb_reachable = await _sandbox_pool_usage()
    failures = await _recent_failures()

    return PlatformStatus(
        counts=CountsByStatus(
            runs=run_counts,
            episodes=ep_counts,
            developer_envs=env_counts,
            bench_jobs=job_counts,
        ),
        in_flight=InFlight(
            active_run_tasks=len(orchestrator._active_run_tasks),
            active_episode_tasks=sum(
                len(s) for s in orchestrator._active_episode_tasks.values()
            ),
            sandbox_port_pool_in_use=sb_in_use,
            sandbox_port_pool_total=sb_total,
            sandbox_reachable=sb_reachable,
        ),
        recent_failures=failures,
        reaper_enabled=bench_settings.enable_orphan_reaper,
    )
