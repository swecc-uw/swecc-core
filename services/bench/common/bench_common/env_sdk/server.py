"""
HTTP adapter server.

Wraps any BaseEnv subclass and exposes the platform's standard HTTP
environment interface (Section 5.2 of the design doc):

    GET  /health
    POST /reset   { "episode_id": "...", "seed": 42, ...scenario_params }
    POST /step    { "episode_id": "...", "action": ... }
    POST /close   { "episode_id": "..." }
    POST /render  { "episode_id": "...", "mode": "text" }

Usage:
    from bench_common.env_sdk import serve
    from my_env import MyEnv

    serve(MyEnv, port=8765)
"""

from __future__ import annotations

import base64
import logging
import math
import time
from typing import Any, Type

import uvicorn
from bench_common.env_sdk.base import BaseEnv
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

log = logging.getLogger(__name__)

# Episode env instances that have not been touched for this many seconds are
# reaped on the next incoming request.  This bounds memory growth when the
# platform drops a connection without calling /close (crash, network loss, etc.).
_EPISODE_TTL_SECONDS: float = 3600.0


class _ResetRequest(BaseModel):
    episode_id: str
    seed: int | None = None
    scenario_params: dict[str, Any] = {}


class _StepRequest(BaseModel):
    episode_id: str
    action: Any


class _CloseRequest(BaseModel):
    episode_id: str


class _RenderRequest(BaseModel):
    episode_id: str
    mode: str = "text"


def _jsonable_payload(data: Any) -> Any:
    if isinstance(data, bytes):
        return base64.b64encode(data).decode("ascii")
    return jsonable_encoder(data)


def _info_payload(info: dict[str, Any]) -> dict[str, Any]:
    return {str(k): _jsonable_payload(v) for k, v in info.items()}


def _reward_payload(reward: Any) -> float:
    value = float(reward)
    if not math.isfinite(value):
        raise ValueError(f"reward must be finite, got {reward!r}")
    return value


def serve(
    env_class: Type[BaseEnv],
    *,
    host: str = "0.0.0.0",
    port: int = 8765,
    log_level: str = "info",
) -> None:
    """
    Start the HTTP adapter server for *env_class*.

    The server manages one env instance per episode_id.  When /close is
    called (or the server shuts down) instances are cleaned up.  Episodes
    that are abandoned without a /close call (e.g. due to network loss) are
    automatically reaped after ``_EPISODE_TTL_SECONDS`` seconds of inactivity.

    Args:
        env_class:  Your BaseEnv subclass (the class, not an instance).
        host:       Bind address (default "0.0.0.0").
        port:       Port to listen on (default 8765).
        log_level:  Uvicorn log level.
    """
    # env instance registry: episode_id -> BaseEnv instance
    _episodes: dict[str, BaseEnv] = {}
    # last-activity timestamps (monotonic) for TTL-based reaping
    _last_seen: dict[str, float] = {}

    def _touch(episode_id: str) -> None:
        _last_seen[episode_id] = time.monotonic()

    def _reap_stale() -> None:
        """Close and evict episodes that have been idle beyond the TTL."""
        cutoff = time.monotonic() - _EPISODE_TTL_SECONDS
        stale = [eid for eid, ts in _last_seen.items() if ts < cutoff]
        for eid in stale:
            env = _episodes.pop(eid, None)
            _last_seen.pop(eid, None)
            if env is not None:
                try:
                    env.close()
                except Exception:
                    pass
            log.warning("reaped_stale_episode", extra={"episode_id": eid})

    app = FastAPI(
        title=f"BenchAnything Env Adapter — {env_class.__name__}",
        version="1.0.0",
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "env": env_class.__name__, "episodes": len(_episodes)}

    @app.post("/reset")
    def reset(req: _ResetRequest) -> dict:
        _reap_stale()

        # Tear down any existing instance for this episode
        if req.episode_id in _episodes:
            try:
                _episodes[req.episode_id].close()
            except Exception:
                pass

        env = env_class()
        _episodes[req.episode_id] = env
        _touch(req.episode_id)

        try:
            obs = env.reset(seed=req.seed, **req.scenario_params)
        except Exception as exc:
            _episodes.pop(req.episode_id, None)
            _last_seen.pop(req.episode_id, None)
            raise HTTPException(status_code=500, detail=str(exc))

        # Env authors can signal a non-JSON content-type and/or an episode-level
        # system prompt by returning a dict with the shape:
        #   {"data": <obs>, "content_type": "image/png", "system_prompt": "..."}
        # This is the only place where reset() can override content_type; for
        # step() observations use StepResult.content_type instead.
        data = obs
        content_type = "application/json"
        system_prompt = None

        if (
            isinstance(obs, dict)
            and "data" in obs
            and ("content_type" in obs or "system_prompt" in obs)
        ):
            data = obs.get("data")
            content_type = obs.get("content_type", content_type)
            system_prompt = obs.get("system_prompt")

        return {
            "data": _jsonable_payload(data),
            "content_type": content_type,
            "system_prompt": system_prompt,
        }

    @app.post("/step")
    def step(req: _StepRequest) -> dict:
        env = _episodes.get(req.episode_id)
        if env is None:
            raise HTTPException(
                status_code=404,
                detail=f"No active episode '{req.episode_id}'. Call /reset first.",
            )
        _touch(req.episode_id)
        try:
            action = env.parse_action(req.action)
            result = env.step(action)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return {
            "observation": {
                "data": _jsonable_payload(result.observation),
                # Use the content_type the env declared on StepResult so that
                # image and multi-modal observations are typed correctly rather
                # than being forced to "application/json".
                "content_type": result.content_type,
            },
            "reward": _reward_payload(result.reward),
            "terminated": bool(result.terminated),
            "truncated": bool(result.truncated),
            "info": _info_payload(result.info),
            "system_prompt": result.system_prompt,
        }

    @app.post("/close")
    def close(req: _CloseRequest) -> dict:
        env = _episodes.pop(req.episode_id, None)
        _last_seen.pop(req.episode_id, None)
        if env is not None:
            try:
                env.close()
            except Exception:
                pass
        return {}

    @app.post("/render")
    def render(req: _RenderRequest) -> dict:
        env = _episodes.get(req.episode_id)
        if env is None:
            raise HTTPException(status_code=404, detail="Episode not found")
        _touch(req.episode_id)
        data = env.render(mode=req.mode)
        content_type = "text/plain" if isinstance(data, str) else "application/json"
        return {"data": _jsonable_payload(data), "content_type": content_type}

    log.info(f"Starting {env_class.__name__} adapter on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level=log_level)
