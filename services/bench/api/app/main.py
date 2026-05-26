"""
FastAPI application entry point.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager

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
from app.routes import auth_routes, bench, developer, leaderboard, runs, techniques, test
from bench_common.config import settings as bench_settings  # noqa: E402
from bench_common.storage.database import init_db  # noqa: E402
from bench_common.storage.trace_store import trace_store  # noqa: E402
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

log = structlog.get_logger()
GATEWAY_PREFIX = bench_settings.gateway_prefix


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
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(PrincipalMiddleware)

app.include_router(auth_routes.router)
app.include_router(domains.router)
app.include_router(runs.router)
app.include_router(test.router)
app.include_router(leaderboard.router)
app.include_router(techniques.router)
app.include_router(developer.router)
app.include_router(bench.router)


@app.get("/")
async def root() -> dict:
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


@app.websocket("/v1/ws/episodes/{episode_id}/trace")
async def stream_trace(websocket: WebSocket, episode_id: str) -> None:
    await websocket.accept()
    sent = 0
    try:
        while True:
            events = await trace_store.read(episode_id)
            for event in events[sent:]:
                await websocket.send_text(event.model_dump_json())
                sent += 1
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                msg = json.loads(data)
                if msg.get("command") == "cancel":
                    break
            except asyncio.TimeoutError:
                pass
            except Exception:
                break
            if events and events[-1].event_type == "episode_end":
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()
