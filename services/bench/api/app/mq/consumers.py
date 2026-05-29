import asyncio
import json
import logging

import structlog
from bench_common.config import settings
from bench_common.orchestrator import service as orchestrator

from . import consumer as mq_consumer

logger = logging.getLogger(__name__)
log = structlog.get_logger()

BENCH_EXCHANGE = "swecc-bench-exchange"


@mq_consumer(
    queue="bench.run-queue",
    exchange=BENCH_EXCHANGE,
    routing_key="bench.run.execute",
    prefetch_count=settings.mq_prefetch,
)
async def consume_run_execute(body, properties):
    message_str = body.decode("utf-8")
    message: dict = json.loads(message_str)
    run_id = message.get("run_id")
    if not run_id:
        log.warning("mq_run_execute_missing_run_id")
        return

    log.info("mq_run_execute_received", run_id=run_id, routing_key="bench.run.execute")
    asyncio.create_task(orchestrator.execute_run(run_id))
