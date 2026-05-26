"""Default URLs for mesocosm (prod vs local dev).

Canonical for the PyPI package — no bench_common import at module load.
bench_common/cli/urls.py mirrors this for server-only installs.
"""

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
