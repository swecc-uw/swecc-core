"""
FastAPI application entry point.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager

# Django bootstrap MUST happen before importing anything that touches the
# bench schema — bench_common.storage.database imports Django models at module
# load time, and routers import bench_common.storage.database transitively.
#
# bench-api uses Docker config server_env (same file as swecc-server). Force our
# settings module — do not use setdefault or server.settings would win if present.
os.environ["DJANGO_SETTINGS_MODULE"] = "app.django_settings"
import django  # noqa: E402
from django.conf import settings as django_settings  # noqa: E402

django.setup()

if "bench.apps.BenchConfig" not in django_settings.INSTALLED_APPS:
    raise RuntimeError(
        "Wrong Django settings loaded (expected app.django_settings). "
        "Unset DJANGO_SETTINGS_MODULE in server_env or ensure bench-api entrypoint runs first."
    )

import structlog  # noqa: E402
from app.middleware.auth import PrincipalMiddleware  # noqa: E402
from app.routes import domains  # noqa: E402
from app.routes import (
    admin,
    auth_routes,
    bench,
    developer,
    gallery,
    leaderboard,
    me_routes,
    runs,
    teams,
    techniques,
    test,
)
from bench_common.config import settings as bench_settings  # noqa: E402
from bench_common.storage.database import init_db  # noqa: E402

try:  # noqa: E402
    from bench_common.storage.database import reap_orphan_work  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - compatibility with older bench_common builds
    async def reap_orphan_work() -> dict[str, int]:
        return {}

from bench_common.storage.trace_store import trace_store  # noqa: E402
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware  # noqa: E402

log = structlog.get_logger()

# Gateway prefix for public URLs (Swagger/OpenAPI). From ORCH_GATEWAY_PREFIX or
# ORCH_PUBLIC_BASE_URL — see bench_common.config.Settings.
GATEWAY_PREFIX = bench_settings.gateway_prefix

# Mesocosm (Vite) and other SPAs send Bearer JWT + credentials; wildcard origin
# is invalid with allow_credentials=True and breaks error responses in browsers.
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "BENCH_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000,"
        "https://mesocosm.swecc.org,https://swecc-uw.github.io",
    ).split(",")
    if o.strip()
]


def _public_path(path: str) -> str:
    return f"{GATEWAY_PREFIX}{path}" if GATEWAY_PREFIX else path


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    log.info("database_ready")
    # Reap rows stranded by the previous process so the UI doesn't show runs
    # "running" forever after a crash/redeploy.  Off by default because a
    # rolling restart with multiple replicas would otherwise mark the OTHER
    # replica's live work as failed.  Enable per-deploy once single-replica
    # is confirmed (or once leases are added).
    if bench_settings.enable_orphan_reaper:
        reaped = await reap_orphan_work()
        if any(reaped.values()):
            log.warning("orphan_work_reaped", **reaped)
    else:
        log.info("orphan_reaper_disabled", hint="set ORCH_ENABLE_ORPHAN_REAPER=true")
    yield


app = FastAPI(
    title="BenchAnything",
    version="0.1.0",
    description="Distributed evaluation protocol for AI agent benchmarks",
    lifespan=lifespan,
    root_path=GATEWAY_PREFIX,
    # SWAG strips /bench/ before proxying; trailing-slash redirects would send
    # Location: http://api.swecc.org/v1/... (drops /bench, wrong scheme) and break
    # Mesocosm CORS even when the canonical path is correct.
    redirect_slashes=False,
)

# ProxyHeaders outermost, then CORS, then Principal — CORS must wrap error responses.
# Pass CORS_ORIGINS into PrincipalMiddleware so it can attach manual CORS headers
# when it has to short-circuit on its own exceptions (CORSMiddleware doesn't get
# a chance to wrap a response that was never produced).
app.add_middleware(PrincipalMiddleware, cors_origins=CORS_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")


def _cors_headers_for_request(request: Request) -> dict[str, str]:
    """Ensure error responses include CORS headers for allowed SPA origins."""
    origin = request.headers.get("origin")
    if origin and origin in CORS_ORIGINS:
        return {
            "access-control-allow-origin": origin,
            "access-control-allow-credentials": "true",
            "vary": "Origin",
        }
    return {}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_request_error", path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=_cors_headers_for_request(request),
    )


app.include_router(auth_routes.router)
app.include_router(gallery.router)
app.include_router(me_routes.router)
app.include_router(teams.router)
app.include_router(domains.router)
app.include_router(runs.router)
app.include_router(test.router)
app.include_router(leaderboard.router)
app.include_router(techniques.router)
app.include_router(developer.router)
app.include_router(bench.router)
app.include_router(admin.router)


@app.get("/")
async def root() -> dict:
    """No API resource here — use /docs, /redoc, or /health (GET / is for humans poking the base URL)."""
    return {
        "service": "BenchAnything",
        "version": "0.1.0",
        "docs": _public_path("/docs"),
        "redoc": _public_path("/redoc"),
        "health": _public_path("/health"),
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


# ── WebSocket trace streaming ─────────────────────────────────────────────────


_TERMINAL_EPISODE_STATUSES = frozenset({"completed", "failed", "cancelled", "timeout", "truncated"})


@app.websocket("/v1/ws/episodes/{episode_id}/trace")
async def stream_trace(websocket: WebSocket, episode_id: str) -> None:
    """
    Stream trace events for an episode in real-time.

    Reads only the new bytes appended since the last tick (not the whole
    file) — without that, a 1000-step episode triggers O(steps^2) Pydantic
    validations per viewer per second.

    Loop exit conditions, in priority order:
      1. Client sent a {"command": "cancel"} message
      2. We observed an ``episode_end`` event
      3. The episode row in the DB is in a terminal status — covers failed
         episodes that never emitted an ``episode_end`` event (e.g. crash
         before the agent loop's finally block), which previously left the
         socket spinning forever.
    """
    from bench_common.storage import database as _db  # local import: avoid cycle

    await websocket.accept()

    offset = 0
    cancelled_by_client = False
    ticks_since_status_check = 0
    try:
        while True:
            events, offset = await trace_store.read_since(episode_id, offset=offset)
            saw_episode_end = False
            for event in events:
                await websocket.send_text(event.model_dump_json())
                if event.event_type == "episode_end":
                    saw_episode_end = True

            # Check for client cancel command.
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                msg = json.loads(data)
                if msg.get("command") == "cancel":
                    cancelled_by_client = True
                    break
            except asyncio.TimeoutError:
                pass
            except Exception:
                break

            if saw_episode_end:
                break

            # DB status check is the safety net for episodes that died before
            # writing episode_end. Only poll every ~5s (10 ticks of 0.5s) so
            # we don't load the DB on every tick for healthy episodes.
            ticks_since_status_check += 1
            if ticks_since_status_check >= 10:
                ticks_since_status_check = 0
                try:
                    ep = await _db.get_episode(episode_id)
                except Exception:
                    ep = None
                if ep is not None and ep.status in _TERMINAL_EPISODE_STATUSES:
                    break

            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        # Client already gone — calling close() now raises 'Unexpected ASGI
        # message websocket.close' on every disconnect. Return without trying.
        return
    finally:
        if not cancelled_by_client:
            try:
                await websocket.close()
            except RuntimeError:
                pass
        else:
            await websocket.close()
