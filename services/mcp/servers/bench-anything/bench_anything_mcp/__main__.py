from __future__ import annotations

import os
import sys

from bench_anything_mcp.server import mcp


def main() -> None:
    if sys.stdin.isatty() and os.environ.get("BENCH_ANYTHING_MCP_ALLOW_TTY", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        print(
            "bench_anything_mcp: stdin is a TTY — this process expects JSON-RPC on stdin from an "
            "MCP host (e.g. Cursor), not an interactive shell.\n"
            "  • Configure the BenchAnything MCP in your client and let it spawn this command.\n"
            "  • Or: npx -y @modelcontextprotocol/inspector  (then point it at this server command).\n"
            "  • To force stdio in a TTY (noisy; you must send valid JSON-RPC only): "
            "BENCH_ANYTHING_MCP_ALLOW_TTY=1",
            file=sys.stderr,
        )
        raise SystemExit(2)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
