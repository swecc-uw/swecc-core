# mcp-host

A small **Starlette gateway** that exposes every MCP server in `services/mcp/servers/` over **Streamable HTTP** so remote agent harnesses can connect by URL — no local subprocess required.

This implements "Shape B" of the layout described in `services/mcp/README.md`. Adding a new MCP under `services/mcp/servers/<name>/` and rebuilding this image is the only step required to publish it; `app/registry.py` walks the folder at startup.

## URL layout

| Endpoint | Purpose |
|---|---|
| `GET /` | Service banner + JSON list of mounted servers |
| `GET /health` | Liveness check |
| `GET /<slug>/` | Per-server discovery JSON (transport, endpoint URL) |
| `POST + GET /<slug>/mcp` | Streamable HTTP endpoint for that MCP server |

`<slug>` is the folder name under `services/mcp/servers/` (kebab-case); the corresponding Python package is `<slug_with_underscores>_mcp` and must export a `mcp = FastMCP(...)` instance from `<package>/server.py`.

## Local dev

From the swecc-core repo root:

```bash
docker compose up mcp-host bench-api bench-sandbox
```

Then point any MCP-capable client at:

```
http://localhost:8009/bench-anything/mcp
```

For Cursor / Claude Code / VS Code (`.cursor/mcp.json` / `~/.config/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "bench-anything": {
      "url": "http://localhost:8009/bench-anything/mcp"
    }
  }
}
```

If you instead run the dev gateway (`docker compose --profile with-nginx up`), the mcp-host is reachable through it at `http://localhost/mcp/bench-anything/mcp` — same shape as production.

## Production URL

mcp-host is **not** exposed on its own subdomain. The shared `api.swecc.org` gateway routes `/mcp/` to it, mirroring how `/bench/` routes to `bench-api`:

```
https://api.swecc.org/mcp/bench-anything/mcp
```

Point any remote agent harness at that URL. The gateway nginx (`infra/nginx.conf` for swarm; `infra/gateway/config/nginx/proxy-confs/api.swecc.org.subdomain.conf` for the SWAG-style deployment) ships with the right `proxy_buffering off` + long timeout settings the Streamable HTTP transport needs.

## How servers find the bench API

The `bench-anything` MCP is a thin client over `bench-api`'s HTTP surface and reads `BENCH_ANYTHING_BASE_URL` to know where it is. The compose entry sets it to `http://swecc-bench-api:8000` (the in-network hostname) so MCP tool calls hit the local bench-api directly. To repoint at the deployed bench-api from a local mcp-host (or to test prod's MCP against staging's bench-api etc.), override that env var on the `mcp-host` service — e.g. `BENCH_ANYTHING_BASE_URL=https://api.swecc.org/bench` in `.env`.

## Adding a new MCP

```bash
mkdir -p services/mcp/servers/<name>/<name>_mcp
# add pyproject.toml exposing the `<name>-mcp` package
# add server.py exporting `mcp = FastMCP("...")`
# rebuild + restart mcp-host
docker compose up -d --build mcp-host
```

The new server appears at `/<name>/mcp` automatically — the gateway scans `services/mcp/servers/` at boot and mounts everything it finds.

## Why Streamable HTTP only

The MCP spec ships two HTTP transports:

| Transport | Status | Notes |
|---|---|---|
| Streamable HTTP | Modern | Single stateful URL; carries both JSON-RPC and the notification stream |
| SSE | Legacy | Pair of endpoints (`/sse` GET + `/messages/...` POST); being deprecated |

All current MCP clients (Cursor, Claude Code, Continue, the official `mcp` CLI inspector) speak Streamable HTTP. Shipping only it keeps the route table clean and avoids the URL-collision tap-dance you'd need to mount both transports under the same per-server prefix. If a client truly needs SSE, run the package over stdio against the local install — the package is also pip-installable directly from `services/mcp/servers/<slug>/`.
