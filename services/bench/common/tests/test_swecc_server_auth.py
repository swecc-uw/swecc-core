from __future__ import annotations

import httpx
import pytest
from bench_common.auth import swecc_server


def _response(
    status: int,
    *,
    json_body: dict | None = None,
    url: str = "https://api.swecc.org/auth/login/",
) -> httpx.Response:
    request = httpx.Request("POST", url)
    return httpx.Response(status, request=request, json=json_body)


def test_format_auth_http_error_masks_invalid_credentials_on_400() -> None:
    response = _response(400, json_body={"detail": "Invalid credentials."})
    assert swecc_server.format_auth_http_error(response) == "Invalid username or password"


def test_format_auth_http_error_masks_missing_fields_on_400() -> None:
    response = _response(
        400,
        json_body={"detail": "Please provide username and password."},
    )
    assert swecc_server.format_auth_http_error(response) == "Invalid username or password"


def test_format_auth_http_error_masks_unauthorized() -> None:
    response = _response(401, json_body={"detail": "Authentication credentials were not provided."})
    assert swecc_server.format_auth_http_error(response) == "Invalid username or password"


def test_format_auth_http_error_includes_403_detail() -> None:
    response = _response(403, json_body={"detail": "User account is disabled."})
    assert swecc_server.format_auth_http_error(response) == (
        "Account access denied: User account is disabled."
    )


def test_format_auth_http_error_403_without_body() -> None:
    response = _response(403)
    assert swecc_server.format_auth_http_error(response) == "Account access denied."


def test_format_auth_http_error_other_status_uses_server_detail() -> None:
    response = _response(500, json_body={"detail": "Internal server error"})
    assert swecc_server.format_auth_http_error(response) == (
        "Authentication failed (HTTP 500): Internal server error"
    )


def test_format_auth_http_error_other_status_without_body() -> None:
    response = _response(502)
    assert swecc_server.format_auth_http_error(response) == "Authentication failed (HTTP 502)"


def test_login_raises_friendly_http_status_error(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("POST", "https://api.swecc.org/auth/login/")
    response = httpx.Response(
        400,
        request=request,
        json={"detail": "Invalid credentials."},
    )
    client = httpx.Client()
    monkeypatch.setattr(swecc_server, "fetch_csrf", lambda *_args, **_kwargs: "csrf")
    monkeypatch.setattr(client, "post", lambda *_args, **_kwargs: response)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        swecc_server.login(client, "https://api.swecc.org", "alice", "wrong-pass")

    assert str(exc_info.value) == "Invalid username or password"
    assert "wrong-pass" not in str(exc_info.value)


def test_fetch_jwt_raises_friendly_http_status_error(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("GET", "https://api.swecc.org/auth/jwt/")
    response = httpx.Response(
        403,
        request=request,
        json={"detail": "Authentication credentials were not provided."},
    )
    client = httpx.Client()
    monkeypatch.setattr(client, "get", lambda *_args, **_kwargs: response)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        swecc_server.fetch_jwt(client, "https://api.swecc.org")

    assert str(exc_info.value) == (
        "Account access denied: Authentication credentials were not provided."
    )
