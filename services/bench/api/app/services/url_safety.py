from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from fastapi import HTTPException

_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
_BLOCKED_SUFFIXES = (".localhost", ".local")


def assert_public_http_url(url: str | None, *, field: str) -> None:
    """Reject obvious SSRF targets in user-supplied remote environment URLs."""
    if not url:
        return
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=422, detail=f"{field} must be an http(s) URL")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise HTTPException(status_code=422, detail=f"{field} must include a hostname")
    if host in _LOCAL_HOSTNAMES or host.endswith(_BLOCKED_SUFFIXES):
        raise HTTPException(
            status_code=422, detail=f"{field} cannot target a local hostname"
        )
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise HTTPException(
            status_code=422, detail=f"{field} cannot target a private IP"
        )
