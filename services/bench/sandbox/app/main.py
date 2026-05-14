"""
Sandbox HTTP service — manages cloned env subprocesses and proxies
traffic from the API container to the appropriate env process.
"""
from __future__ import annotations

from typing import Any

import httpx
import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import manager

log = structlog.get_logger()

app = FastAPI(title="BenchAnything Sandbox", version="0.1.0")


# ── Internal management routes ─────────────────────────────────────────────────

class CloneRequest(BaseModel):
    env_id: str
    github_url: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/clone")
async def clone(req: CloneRequest) -> dict[str, Any]:
    try:
        result = await manager.clone_and_start(req.env_id, req.github_url)
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/envs/{env_id}/status")
async def env_status(env_id: str) -> dict[str, Any]:
    status = manager.get_status(env_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Env '{env_id}' not registered")
    return status


@app.delete("/envs/{env_id}")
async def stop_env(env_id: str) -> dict[str, str]:
    await manager.stop_env(env_id)
    return {"status": "stopped"}


# ── Reverse-proxy to env subprocesses ─────────────────────────────────────────

@app.api_route("/envs/{env_id}/{path:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH"])
async def proxy_to_env(env_id: str, path: str, request: Request) -> Response:
    """
    Proxy requests from the API container (which uses env_url = http://sandbox:8001/envs/{id})
    down to the local subprocess running at localhost:{port}.
    HttpEnvClient calls: {env_url}/reset, {env_url}/step, {env_url}/close, {env_url}/health
    """
    port = manager.get_env_port(env_id)
    if port is None:
        raise HTTPException(status_code=404, detail=f"Env '{env_id}' is not running")

    target_url = f"http://localhost:{port}/{path}"

    body = await request.body()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers=headers,
                params=dict(request.query_params),
            )
        except httpx.TransportError as exc:
            raise HTTPException(status_code=502, detail=f"Env server unreachable: {exc}")

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
        media_type=resp.headers.get("content-type"),
    )
