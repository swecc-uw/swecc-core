import asyncio
import json
import logging

import structlog
from bench_common.config import settings

from . import consumer as mq_consumer

logger = logging.getLogger(__name__)
log = structlog.get_logger()

BENCH_EXCHANGE = "swecc-bench-exchange"


@mq_consumer(
    queue="bench.job-queue",
    exchange=BENCH_EXCHANGE,
    routing_key="bench.job.execute",
    prefetch_count=settings.mq_prefetch,
)
async def consume_job_execute(body, properties):
    message_str = body.decode("utf-8")
    message: dict = json.loads(message_str)
    job_id = message.get("job_id")
    if not job_id:
        log.warning("mq_job_execute_missing_job_id")
        return

    log.info("mq_job_execute_received", job_id=job_id, routing_key="bench.job.execute")
    asyncio.create_task(_process_bench_job(job_id))


async def _process_bench_job(job_id: str) -> None:
    from app.worker import run_full_bench
    from bench_common.storage import database as db

    job = await db.claim_bench_job(job_id)
    if job is None:
        log.info("mq_job_execute_skip_claim", job_id=job_id)
        return

    log.info("mq_job_execute_start", job_id=job_id, env_id=job.get("env_id"))
    try:
        model_results = await run_full_bench(job)
        await db.complete_bench_job(job_id, model_results, failed=False)
        log.info("mq_job_execute_complete", job_id=job_id)
    except Exception:
        log.exception("mq_job_execute_failed", job_id=job_id)
        await db.complete_bench_job(job_id, {}, failed=True)
