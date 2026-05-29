"""Swagger UI must load OpenAPI from the gateway-prefixed path when behind /bench/."""

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _openapi_url_from_swagger_html(html: str) -> str | None:
    match = re.search(r"url: '([^']+)'", html)
    return match.group(1) if match else None


def test_fastapi_root_path_prefixes_openapi_url_in_swagger():
    """Document expected FastAPI behavior used by bench-api (root_path=ORCH_GATEWAY_PREFIX)."""
    app = FastAPI(root_path="/bench")
    client = TestClient(app)
    assert (
        _openapi_url_from_swagger_html(client.get("/docs").text)
        == "/bench/openapi.json"
    )
