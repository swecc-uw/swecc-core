"""
Discover MCP server packages under /app/servers and import the FastMCP
instance each one exports. Convention (set in services/mcp/README.md):

    services/mcp/servers/<name>/<name>_mcp/server.py     # exports `mcp`
    services/mcp/servers/<name>/pyproject.toml

The folder is kebab-case for the filesystem; the Python package is the same
name with hyphens turned into underscores plus an `_mcp` suffix.

Adding a new MCP just means dropping a new folder in `servers/` and rebuilding
the mcp-host image — no edits here required.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import FastMCP

log = logging.getLogger(__name__)

SERVERS_ROOT = Path(__file__).resolve().parent.parent / "servers"


@dataclass(frozen=True)
class MountedServer:
    """A discovered MCP server ready to be mounted by main.py."""

    slug: str  # url-safe folder name, e.g. "bench-anything"
    package: str  # python module path, e.g. "bench_anything_mcp.server"
    mcp: FastMCP


def _slug_to_package(slug: str) -> str:
    """`bench-anything` → `bench_anything_mcp.server` (matches our convention)."""
    return f"{slug.replace('-', '_')}_mcp.server"


def discover() -> list[MountedServer]:
    """Walk SERVERS_ROOT, import each <name>_mcp.server, collect its `mcp`."""
    servers: list[MountedServer] = []
    if not SERVERS_ROOT.exists():
        log.warning("mcp servers root missing: %s", SERVERS_ROOT)
        return servers

    for child in sorted(SERVERS_ROOT.iterdir()):
        if not child.is_dir() or not (child / "pyproject.toml").exists():
            continue
        slug = child.name
        module_path = _slug_to_package(slug)
        try:
            module = importlib.import_module(module_path)
        except Exception:  # noqa: BLE001 — keep the host up even if one server fails
            log.exception("failed to import MCP server %s (%s)", slug, module_path)
            continue
        mcp = getattr(module, "mcp", None)
        if not isinstance(mcp, FastMCP):
            log.warning(
                "MCP server %s did not export a FastMCP instance named `mcp` (got %r)",
                slug,
                type(mcp).__name__,
            )
            continue
        servers.append(MountedServer(slug=slug, package=module_path, mcp=mcp))
        log.info("discovered MCP server: %s -> %s", slug, module_path)
    return servers
