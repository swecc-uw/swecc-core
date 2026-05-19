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
from app.routes import bench, developer, domains, leaderboard, runs, techniques, test  # noqa: E402
from bench_common.storage.database import init_db  # noqa: E402
from bench_common.storage.trace_store import trace_store  # noqa: E402
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

log = structlog.get_logger()


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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
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
