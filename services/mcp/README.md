# mcp

Home for MCP (Model Context Protocol) server packages produced by the swecc-core ecosystem. The folder is built to grow: each MCP is its own package under `servers/<name>/`, freely added or removed without touching the others.

## Layout

```
services/mcp/
├── README.md
├── host/                               # Streamable HTTP gateway (Shape B)
│   ├── Dockerfile / requirements.txt
│   └── app/main.py + app/registry.py   # mounts every servers/<x> at /<x>/mcp
└── servers/
    └── bench-anything/                 # the BenchAnything MCP, ported from upstream
        ├── pyproject.toml
        └── bench_anything_mcp/
            ├── __init__.py / __main__.py
            ├── server.py / client.py / infer.py / artifacts.py / validation.py / settings.py
            └── rules/                  # MCP rule prompts shipped with the package
```

The repo ships **both shapes** below — pick whichever matches how the client wants to consume MCPs.

## Shape A — local stdio (per-client subprocess)

Each subfolder under `servers/` is also an installable Python package launched **per-client** over stdio (the original MCP transport). Best for IDE-side hosts that spawn the server themselves and don't want network hops.

```bash
pip install -e ./services/mcp/servers/bench-anything
```

Then configure your MCP client. Example for Cursor / VS Code (`.cursor/mcp.json` or `~/.config/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "bench-anything": {
      "command": "python",
      "args": ["-m", "bench_anything_mcp"],
      "env": {
        "BENCH_ANYTHING_BASE_URL": "http://127.0.0.1:8010"
      }
    }
  }
}
```

(Note: `8010` is the host port `bench-api` binds to via docker compose. Set `8000` if you're running the FastAPI directly via `uvicorn`.)

## Shape B — remote Streamable HTTP (the `mcp-host` service)

For consumers that can't spawn a subprocess (a deployed agent in the swarm, a CI job, a remote harness on someone else's laptop) the `mcp-host` Starlette gateway in `services/mcp/host/` mounts every package under `servers/*` at `/<slug>/mcp` over Streamable HTTP. One container, many servers, one URL per server.

```bash
docker compose up mcp-host bench-api bench-sandbox
```

Then point any MCP-capable client at:

| Environment | URL |
|---|---|
| Local dev (no nginx) | `http://localhost:8009/bench-anything/mcp` |
| Local dev (`--profile with-nginx`) | `http://localhost/mcp/bench-anything/mcp` |
| Production | `https://api.swecc.org/mcp/bench-anything/mcp` |

In production, `mcp-host` does **not** live on its own subdomain. The shared `api.swecc.org` gateway routes `/mcp/` to it (see `infra/nginx.conf` and `infra/gateway/config/nginx/proxy-confs/api.swecc.org.subdomain.conf`), so it inherits the existing cert + DNS — same trick `/bench/` uses for `bench-api`.

Full host docs (URL layout, why Streamable HTTP only, etc.) live in [`host/README.md`](./host/README.md).

## Adding a new MCP server

```bash
mkdir -p services/mcp/servers/<name>/<name>_mcp
# add pyproject.toml exposing `<name>-mcp` package
# add server.py exporting `mcp = FastMCP("...")`
docker compose up -d --build mcp-host
```

The new server appears at `/<name>/mcp` automatically — `host/app/registry.py` scans `servers/` at boot and mounts everything it finds. No edits to `mcp-host` required.

**Convention:** folder name is kebab-case (`bench-anything`), Python package is snake_case with a `_mcp` suffix (`bench_anything_mcp`), and `<package>/server.py` must export `mcp = FastMCP(...)` at module scope.
