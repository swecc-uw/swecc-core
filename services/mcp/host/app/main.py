"""
mcp-host: Starlette gateway that exposes every discovered FastMCP server over
the Model Context Protocol's **Streamable HTTP** transport. One container,
many servers, one URL per server. Lets remote agent harnesses (Cursor, Claude
Code, Continue, custom MCP clients, etc.) connect by URL — no need to spawn a
local subprocess.

URL layout (per discovered server `slug`):

    /<slug>/mcp     — Streamable HTTP endpoint (single stateful URL the
                      client POSTs JSON-RPC to and GETs an SSE stream from)
    /<slug>/        — JSON discovery payload for that server

Top-level helpers:

    /                — service banner + list of mounted servers
    /health          — { "status": "ok", "servers": [...] }

We deliberately ship only Streamable HTTP (the modern transport). It carries
both request/response and the legacy SSE "stream of notifications" over a
single endpoint, so every current MCP client speaks it. If a client truly
needs the old standalone SSE transport, run it via stdio against the package
directly (it lives at services/mcp/servers/<slug>/) — the host can be extended
to mount sse_app() under a separate prefix later.

References:
    https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/examples/snippets/servers/streamable_http_multiple_servers.py
"""
from __future__ import annotations

import contextlib
import logging
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from app.registry import MountedServer, discover

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("mcp-host")

# Discover at import time so build failures (missing module, bad export, etc.)
# surface before uvicorn starts taking traffic.
SERVERS: list[MountedServer] = discover()

# Each FastMCP exposes its streamable endpoint at `streamable_http_path`
# (default "/mcp"). Mounting the returned app at `/<slug>` therefore yields
# the public URL `/<slug>/mcp`. We also force `json_response=False` (default)
# so the endpoint streams chunked JSON — required for tools that emit
# progressive output.
for s in SERVERS:
    s.mcp.settings.streamable_http_path = "/mcp"


@contextlib.asynccontextmanager
async def lifespan(_app: Starlette):
    """Run every server's session manager for the lifetime of the process."""
    async with contextlib.AsyncExitStack() as stack:
        for s in SERVERS:
            await stack.enter_async_context(s.mcp.session_manager.run())
            log.info("mounted MCP server %s at /%s/mcp", s.slug, s.slug)
        yield


def _server_descriptor(s: MountedServer) -> dict[str, Any]:
    return {
        "slug": s.slug,
        "name": s.mcp.name,
        "package": s.package,
        "transport": "streamable-http",
        "endpoint": f"/{s.slug}/mcp",
    }


async def root(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "service": "swecc-mcp-host",
            "transport": "streamable-http",
            "servers": [_server_descriptor(s) for s in SERVERS],
            "docs": (
                "Connect any MCP-capable agent harness (Cursor, Claude Code, "
                "Continue, etc.) to /<slug>/mcp. The URL is a single stateful "
                "endpoint the client POSTs JSON-RPC to and GETs an SSE-style "
                "stream from."
            ),
        }
    )


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "servers": [s.slug for s in SERVERS]})


def _make_descriptor_handler(server: MountedServer):
    """Bind the server's slug into a closure so Route handlers don't need a
    path parameter (we deliberately register each server's discovery URL
    individually so unknown slugs fall through to the Starlette default 404)."""
    descriptor = _server_descriptor(server)

    async def handler(_request: Request) -> JSONResponse:
        return JSONResponse(descriptor)

    return handler


# Order matters: explicit / and /health first, then per-server descriptor at
# /<slug>/, then per-server Mount so streamable HTTP resolves under each
# prefix. Putting the descriptor route before the Mount means GET /<slug>/
# returns JSON instead of falling through into the FastMCP app (which would
# 404 there).
routes: list[Any] = [
    Route("/", root),
    Route("/health", health),
]
for s in SERVERS:
    routes.append(Route(f"/{s.slug}/", _make_descriptor_handler(s)))
    routes.append(Mount(f"/{s.slug}", app=s.mcp.streamable_http_app()))

app = Starlette(routes=routes, lifespan=lifespan)
