"""HTTP client for existing swecc-server auth endpoints (engagement-compatible)."""

from __future__ import annotations

import json

import httpx


def fetch_csrf(client: httpx.Client, server_url: str) -> str | None:
    base = server_url.rstrip("/")
    r = client.get(f"{base}/auth/csrf/")
    r.raise_for_status()
    return r.headers.get("x-csrftoken") or r.headers.get("X-CSRFToken")


def _extract_json_message(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        return None
    for key in ("detail", "error", "message"):
        value = body.get(key)
        if value is not None:
            if isinstance(value, str):
                return value
            return json.dumps(value)
    return None


def format_auth_http_error(response: httpx.Response) -> str:
    """User-facing message for swecc-server auth HTTP failures."""
    status = response.status_code
    if status in (400, 401):
        return "Invalid username or password"
    if status == 403:
        detail = _extract_json_message(response)
        if detail:
            return f"Account access denied: {detail}"
        return "Account access denied."
    detail = _extract_json_message(response)
    if detail:
        return f"Authentication failed (HTTP {status}): {detail}"
    return f"Authentication failed (HTTP {status})"


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
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise httpx.HTTPStatusError(
            format_auth_http_error(exc.response),
            request=exc.request,
            response=exc.response,
        ) from None


def fetch_jwt(client: httpx.Client, server_url: str) -> str:
    base = server_url.rstrip("/")
    r = client.get(f"{base}/auth/jwt/")
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise httpx.HTTPStatusError(
            format_auth_http_error(exc.response),
            request=exc.request,
            response=exc.response,
        ) from None
    data = r.json()
    token = data.get("token")
    if not token:
        raise ValueError("No token in /auth/jwt/ response")
    if isinstance(token, bytes):
        token = token.decode()
    return str(token)
