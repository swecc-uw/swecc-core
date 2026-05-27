"""Shared default URLs for mesocosm / bench_common CLI (prod vs local dev)."""

from __future__ import annotations

import os

PROD_SERVER_URL = "https://api.swecc.org"
PROD_BENCH_API_URL = "https://api.swecc.org/bench"
LOCAL_SERVER_URL = "http://127.0.0.1:8000"
LOCAL_BENCH_API_URL = "http://127.0.0.1:8010"
LOCAL_ENV_ADAPTER_URL = "http://127.0.0.1:8765"


def mesocosm_local_mode() -> bool:
    """True when ``MESOCOSM_LOCAL`` is set (local docker + adapter dev loop)."""
    return os.environ.get("MESOCOSM_LOCAL", "").strip().lower() in ("1", "true", "yes", "on")


def _bench_url_from_env() -> str | None:
    for key in ("MESOCOSM_BASE_URL", "SWECC_BENCH_URL", "BENCH_API_URL"):
        val = os.environ.get(key, "").strip()
        if val:
            return val.rstrip("/")
    return None


def default_bench_api_url() -> str:
    """bench-api base URL (includes ``/bench`` in production behind SWAG)."""
    from_env = _bench_url_from_env()
    if from_env:
        return from_env
    if mesocosm_local_mode():
        return LOCAL_BENCH_API_URL
    return PROD_BENCH_API_URL


def guest_bench_api_url() -> str:
    """bench-api URL for ``auth guest`` (production default; ignores creds and ``MESOCOSM_LOCAL``)."""
    from_env = _bench_url_from_env()
    if from_env:
        return from_env
    return PROD_BENCH_API_URL


def is_local_server_url(server_url: str) -> bool:
    server = server_url.rstrip("/")
    if server == LOCAL_SERVER_URL:
        return True
    return "127.0.0.1:8000" in server or "localhost:8000" in server


def is_local_bench_api_url(bench_url: str) -> bool:
    bench = bench_url.rstrip("/")
    if bench == LOCAL_BENCH_API_URL:
        return True
    return "127.0.0.1:8010" in bench or "localhost:8010" in bench


def is_stale_local_bench_url(bench_url: str, *, server_url: str) -> bool:
    """Saved localhost bench URL while member auth used a remote swecc-server."""
    return is_local_bench_api_url(bench_url) and not is_local_server_url(server_url)


def bench_url_from_server(server_url: str) -> str:
    """Derive bench-api base URL from swecc-server URL (prod → ``/bench`` path)."""
    server = server_url.rstrip("/")
    if server == PROD_SERVER_URL or "api.swecc.org" in server:
        return PROD_BENCH_API_URL
    if is_local_server_url(server):
        return LOCAL_BENCH_API_URL
    if server.endswith("/bench"):
        return server
    return f"{server}/bench"


def member_bench_api_url(
    *,
    server_url: str | None = None,
    cli_bench_url: str | None = None,
    creds: dict | None = None,
) -> str:
    """Resolve bench-api URL for member sessions (login, teams, runs, …)."""
    if cli_bench_url:
        return cli_bench_url.rstrip("/")
    from_env = _bench_url_from_env()
    if from_env:
        return from_env

    server = (server_url or (creds or {}).get("server_url") or "").strip()
    saved = (creds or {}).get("bench_url")

    if server and saved and is_stale_local_bench_url(saved, server_url=server):
        return bench_url_from_server(server)

    if saved:
        return saved.rstrip("/")

    if server:
        if mesocosm_local_mode() and is_local_server_url(server):
            return LOCAL_BENCH_API_URL
        return bench_url_from_server(server)

    if mesocosm_local_mode():
        return LOCAL_BENCH_API_URL
    return PROD_BENCH_API_URL


def whoami_bench_api_url(
    *,
    cli_bench_url: str | None = None,
    creds: dict | None = None,
) -> str:
    """Resolve bench-api URL for ``auth whoami`` (guest ignores ``MESOCOSM_LOCAL`` default)."""
    creds = creds or {}
    if cli_bench_url:
        return cli_bench_url.rstrip("/")
    from_env = _bench_url_from_env()
    if from_env:
        return from_env

    if creds.get("mode") == "guest":
        if creds.get("bench_url"):
            return creds["bench_url"].rstrip("/")
        return guest_bench_api_url()

    return member_bench_api_url(
        server_url=creds.get("server_url"),
        creds=creds,
    )


def default_server_url() -> str:
    """swecc-server base URL (member auth: /auth/login/, /auth/jwt/)."""
    val = os.environ.get("SWECC_SERVER_URL", "").strip()
    if val:
        return val.rstrip("/")
    if mesocosm_local_mode():
        return LOCAL_SERVER_URL
    return PROD_SERVER_URL


def default_env_adapter_url() -> str:
    """Local env HTTP server (``python adapter.py`` — default port 8765)."""
    for key in ("MESOCOSM_ENV_URL", "MESOCOSM_ADAPTER_URL"):
        val = os.environ.get(key, "").strip()
        if val:
            return val.rstrip("/")
    return LOCAL_ENV_ADAPTER_URL
