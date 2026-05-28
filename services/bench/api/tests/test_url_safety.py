from __future__ import annotations

import pytest
from app.services.url_safety import assert_public_http_url
from fastapi import HTTPException


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8765",
        "http://127.0.0.1:8765",
        "http://0.0.0.0:8765",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/env",
        "http://172.16.0.10/env",
        "http://192.168.1.2/env",
        "file:///tmp/env.sock",
        "http://dev.local/env",
    ],
)
def test_assert_public_http_url_rejects_ssrf_targets(url: str) -> None:
    with pytest.raises(HTTPException):
        assert_public_http_url(url, field="env_url")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/env",
        "http://8.8.8.8:8765",
        None,
    ],
)
def test_assert_public_http_url_accepts_public_http_urls(url: str | None) -> None:
    assert_public_http_url(url, field="env_url")
