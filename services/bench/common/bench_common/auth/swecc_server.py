"""HTTP client for existing swecc-server auth endpoints (engagement-compatible)."""

from __future__ import annotations

import httpx


def fetch_csrf(client: httpx.Client, server_url: str) -> str | None:
    base = server_url.rstrip("/")
    r = client.get(f"{base}/auth/csrf/")
    r.raise_for_status()
    return r.headers.get("x-csrftoken") or r.headers.get("X-CSRFToken")


def login(client: httpx.Client, server_url: str, username: str, password: str) -> None:
    base = server_url.rstrip("/")
    token = fetch_csrf(client, server_url)
    headers = {}
    if token:
        headers["X-CSRFToken"] = token
    r = client.post(
        f"{base}/auth/login/",
        json={"username": username.strip(), "password": password},
        headers=headers,
    )
    r.raise_for_status()


def fetch_jwt(client: httpx.Client, server_url: str) -> str:
    base = server_url.rstrip("/")
    r = client.get(f"{base}/auth/jwt/")
    r.raise_for_status()
    data = r.json()
    token = data.get("token")
    if not token:
        raise ValueError("No token in /auth/jwt/ response")
    if isinstance(token, bytes):
        token = token.decode()
    return str(token)
