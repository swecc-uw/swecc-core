# bench-anything-mcp

MCP server that exposes the BenchAnything platform tools (run benches, inspect domains, fetch leaderboards, validate manifests) to MCP clients like Cursor, Claude Code, and Continue.

## Install

```bash
pip install -e .
```

## Run

```bash
BENCH_ANYTHING_BASE_URL=http://127.0.0.1:8000 python -m bench_anything_mcp
```

The platform (`bench-api`) must be reachable at `BENCH_ANYTHING_BASE_URL` before tool calls will succeed.

## Cursor / Claude Code config

```json
{
  "mcpServers": {
    "bench-anything": {
      "command": "python",
      "args": ["-m", "bench_anything_mcp"],
      "env": {
        "BENCH_ANYTHING_BASE_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```
