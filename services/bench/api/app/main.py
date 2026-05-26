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
from bench_common.config import settings as bench_settings  # noqa: E402
from bench_common.storage.database import init_db  # noqa: E402
from bench_common.storage.trace_store import trace_store  # noqa: E402
from fastapi import (FastAPI, Request, WebSocket,  # noqa: E402
                     WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from app.middleware.auth import PrincipalMiddleware  # noqa: E402
from app.routes import (auth_routes, bench, developer, domains,  # noqa: E402
                        gallery, leaderboard, me_routes, runs, teams,
                        techniques, test)

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
    yield


app = FastAPI(
    title="BenchAnything",
    version="0.1.0",
    description="Distributed evaluation protocol for AI agent benchmarks",
    lifespan=lifespan,
    root_path=GATEWAY_PREFIX,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(PrincipalMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_request_error", path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


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


@app.websocket("/v1/ws/episodes/{episode_id}/trace")
async def stream_trace(websocket: WebSocket, episode_id: str) -> None:
    """
    Stream trace events for an episode in real-time.
    Sends all existing events first, then tails the file for new ones.
    Client can send {"command": "cancel"} to disconnect cleanly.
    """
    await websocket.accept()

    sent = 0
    try:
        while True:
            events = await trace_store.read(episode_id)
            for event in events[sent:]:
                await websocket.send_text(event.model_dump_json())
                sent += 1

            # Check for client commands
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                msg = json.loads(data)
                if msg.get("command") == "cancel":
                    break
            except asyncio.TimeoutError:
                pass
            except Exception:
                break

            # Check if episode is done
            if events and events[-1].event_type == "episode_end":
                break

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()
