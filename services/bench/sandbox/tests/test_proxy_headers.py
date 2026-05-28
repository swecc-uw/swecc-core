from __future__ import annotations

from app.main import _forward_headers


def test_forward_headers_strips_credentials_and_hop_by_hop_headers() -> None:
    assert _forward_headers(
        {
            "Authorization": "Bearer secret",
            "Cookie": "session=secret",
            "Host": "sandbox",
            "Content-Length": "123",
            "X-Api-Key": "secret",
            "Content-Type": "application/json",
            "X-Trace-Id": "trace",
        }
    ) == {
        "Content-Type": "application/json",
        "X-Trace-Id": "trace",
    }
