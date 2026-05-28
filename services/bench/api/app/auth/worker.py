"""Service-to-service auth for the EC2 bench worker."""

from __future__ import annotations

import os

import structlog
from app.auth.resolve import auth_disabled
from fastapi import HTTPException, Request

log = structlog.get_logger()


def _expected_worker_token() -> str | None:
    return os.environ.get("BENCH_WORKER_TOKEN") or os.environ.get("SWECC_BENCH_WORKER_TOKEN")


async def require_worker(request: Request) -> None:
    if auth_disabled():
        return
    expected = _expected_worker_token()
    if not expected:
        # Fail closed.  Previously this returned silently, leaving every
        # /v1/bench/jobs* endpoint open to anyone on the internet — they could
        # claim/complete/fail jobs and poison model_results / drain budget.
        log.error("worker_token_unset", hint="set BENCH_WORKER_TOKEN in bench-api env")
        raise HTTPException(
            status_code=503,
            detail="Worker authentication is misconfigured on this deployment.",
        )
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:].strip() != expected:
        raise HTTPException(status_code=401, detail="Worker authentication required")
