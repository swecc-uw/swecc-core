"""Optional RabbitMQ publishers registered by bench-api at startup."""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from bench_common.config import settings

_publish_run: Optional[Callable[[dict], Awaitable[None]]] = None


def register_run_publisher(fn: Callable[[dict], Awaitable[None]]) -> None:
    global _publish_run
    _publish_run = fn


async def publish_run_if_mq(run_id: str) -> None:
    if not settings.mq_enabled:
        return
    if _publish_run is None:
        raise RuntimeError("ORCH_MQ_ENABLED is set but no run publisher is registered")
    await _publish_run({"run_id": run_id})
