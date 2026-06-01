"""Background sweep for runs stuck without in-process execution."""

from __future__ import annotations

import asyncio

import structlog
from app.redis_client import try_claim_run_dispatch
from bench_common.config import settings
from bench_common.mq_dispatch import publish_run_if_mq
from bench_common.orchestrator import service as orchestrator
from bench_common.storage import database as db

log = structlog.get_logger()


async def stale_run_watchdog_loop() -> None:
    interval = max(15, settings.watchdog_interval_seconds)
    while True:
        await asyncio.sleep(interval)
        try:
            await tick_stale_run_watchdog()
        except Exception:
            log.exception("stale_run_watchdog_tick_failed")


async def tick_stale_run_watchdog() -> None:
    if not settings.enable_stale_watchdog:
        return

    rescued = 0
    for run_id in await db.list_stale_run_ids(
        min_age_seconds=settings.stale_run_rescue_seconds,
        limit=50,
    ):
        if orchestrator.run_is_active_locally(run_id):
            continue
        if not await try_claim_run_dispatch(run_id):
            continue
        if settings.mq_enabled:
            try:
                await publish_run_if_mq(run_id)
                log.info("stale_run_requeued", run_id=run_id)
                rescued += 1
                continue
            except Exception:
                log.exception("stale_run_requeue_failed", run_id=run_id)
        asyncio.create_task(orchestrator.dispatch_run_execute(run_id))
        log.info("stale_run_rescue_dispatched", run_id=run_id)
        rescued += 1

    failed: dict[str, int] = {}
    if settings.stale_run_fail_seconds > 0:
        failed = await db.reap_stale_work(
            stale_after_seconds=settings.stale_run_fail_seconds,
            reason="stale_run_timeout",
        )
        if any(failed.values()):
            log.warning("stale_run_watchdog_reaped", rescued=rescued, **failed)
    elif rescued:
        log.info("stale_run_watchdog_rescued", count=rescued)
