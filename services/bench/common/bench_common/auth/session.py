"""Authenticated HTTP session for bench-api calls."""

from __future__ import annotations

import os
from typing import Any

import httpx
from bench_common.auth.credentials import load_credentials


class BenchSession:
    def __init__(self, bench_url: str, token: str, mode: str, active_team_id: str | None = None):
        self.bench_url = bench_url.rstrip("/")
        self.token = token
        self.mode = mode
        self.active_team_id = active_team_id
        self._client = httpx.Client(
            base_url=self.bench_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=120.0,
        )

    @property
    def client(self) -> httpx.Client:
        return self._client

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BenchSession:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def get_bench_session(
    *,
    bench_url: str | None = None,
    token: str | None = None,
) -> BenchSession:
    if os.environ.get("BENCH_AUTH_DISABLED", "").lower() in ("1", "true", "yes"):
        return BenchSession(
            bench_url or os.environ.get("BENCH_API_URL", "http://localhost:8010"),
            token="",
            mode="member",
        )

    creds = load_credentials()
    env_token = (
        token or os.environ.get("SWECC_BENCH_TOKEN") or os.environ.get("SWECC_BENCH_GUEST_TOKEN")
    )
    if env_token:
        mode = "guest" if os.environ.get("SWECC_BENCH_GUEST_TOKEN") else "member"
        return BenchSession(
            (
                bench_url or creds.get("bench_url", "http://localhost:8010")
                if creds
                else "http://localhost:8010"
            ),
            token=env_token,
            mode=mode,
            active_team_id=creds.get("active_team_id") if creds else None,
        )

    if creds and creds.get("token"):
        return BenchSession(
            bench_url or creds.get("bench_url", "http://localhost:8010"),
            token=creds["token"],
            mode=creds.get("mode", "member"),
            active_team_id=creds.get("active_team_id"),
        )

    raise RuntimeError("Not authenticated. Run: bench auth login  (member)  or  bench auth guest")
