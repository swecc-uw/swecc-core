"""Run submission cooldown (Redis SET NX + TTL)."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from app.auth import policy
from app.auth.policy import assert_run_submission_cooldown
from fastapi import HTTPException


def _patch_cooldown_settings(monkeypatch, *, seconds: int) -> None:
    monkeypatch.setattr(
        policy,
        "settings",
        SimpleNamespace(run_submission_cooldown_seconds=seconds),
    )


class _FakeRedis:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, float | None]] = {}

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool:
        now = time.monotonic()
        self._expire_stale(now)
        if nx and key in self._entries:
            return False
        expires_at = (now + ex) if ex else None
        self._entries[key] = (value, expires_at)
        return True

    async def ttl(self, key: str) -> int:
        now = time.monotonic()
        self._expire_stale(now)
        entry = self._entries.get(key)
        if entry is None:
            return -2
        _, expires_at = entry
        if expires_at is None:
            return -1
        remaining = int(expires_at - now)
        return max(remaining, 0)

    def _expire_stale(self, now: float) -> None:
        expired = [
            k for k, (_, exp) in self._entries.items() if exp is not None and exp <= now
        ]
        for key in expired:
            del self._entries[key]


@pytest.fixture
def fake_redis(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr("app.redis_client.get_redis", lambda: client)
    return client


@pytest.mark.asyncio
async def test_first_submission_allowed(fake_redis, monkeypatch):
    monkeypatch.setattr("app.auth.policy.auth_disabled", lambda: False)
    _patch_cooldown_settings(monkeypatch, seconds=120)
    await assert_run_submission_cooldown("member:42")


@pytest.mark.asyncio
async def test_second_submission_within_cooldown_rejected(fake_redis, monkeypatch):
    monkeypatch.setattr("app.auth.policy.auth_disabled", lambda: False)
    _patch_cooldown_settings(monkeypatch, seconds=120)
    await assert_run_submission_cooldown("member:42")
    with pytest.raises(HTTPException) as exc:
        await assert_run_submission_cooldown("member:42")
    assert exc.value.status_code == 429
    assert "wait" in exc.value.detail.lower()
    retry_after = int(exc.value.headers.get("Retry-After", "0"))
    assert 1 <= retry_after <= 120


@pytest.mark.asyncio
async def test_cooldown_disabled_when_seconds_zero(fake_redis, monkeypatch):
    monkeypatch.setattr("app.auth.policy.auth_disabled", lambda: False)
    _patch_cooldown_settings(monkeypatch, seconds=0)
    await assert_run_submission_cooldown("member:42")
    await assert_run_submission_cooldown("member:42")


@pytest.mark.asyncio
async def test_cooldown_skipped_when_auth_disabled(monkeypatch):
    monkeypatch.setattr("app.auth.policy.auth_disabled", lambda: True)
    _patch_cooldown_settings(monkeypatch, seconds=120)
    await assert_run_submission_cooldown("local")
