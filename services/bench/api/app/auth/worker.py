"""Service-to-service auth for the EC2 bench worker."""

from __future__ import annotations

import os

from app.auth.resolve import auth_disabled
from fastapi import HTTPException, Request


def _expected_worker_token() -> str | None:
    return os.environ.get("BENCH_WORKER_TOKEN") or os.environ.get("SWECC_BENCH_WORKER_TOKEN")


async def require_worker(request: Request) -> None:
    if auth_disabled():
        return
    expected = _expected_worker_token()
    if not expected:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:].strip() != expected:
        raise HTTPException(status_code=401, detail="Worker authentication required")
