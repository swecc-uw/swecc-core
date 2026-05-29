import json

from . import producer as mq_producer

BENCH_EXCHANGE = "swecc-bench-exchange"


def build_run_execute_body(data: dict) -> bytes:
    run_id = data.get("run_id")
    if not run_id:
        raise ValueError("run_id is required")
    return json.dumps({"run_id": run_id}).encode("utf-8")


def build_job_execute_body(data: dict) -> bytes:
    job_id = data.get("job_id")
    if not job_id:
        raise ValueError("job_id is required")
    return json.dumps({"job_id": job_id}).encode("utf-8")


@mq_producer(exchange=BENCH_EXCHANGE, routing_key="bench.run.execute")
async def publish_run_execute(data: dict) -> bytes:
    return build_run_execute_body(data)


@mq_producer(exchange=BENCH_EXCHANGE, routing_key="bench.job.execute")
async def publish_job_execute(data: dict) -> bytes:
    return build_job_execute_body(data)
