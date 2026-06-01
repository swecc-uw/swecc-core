"""Tests for stale-run watchdog rescue behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.watchdog import tick_stale_run_watchdog
from bench_common.config import settings


@pytest.mark.asyncio
async def test_watchdog_dispatches_locally_even_after_mq_requeue(monkeypatch) -> None:
    """Requeue alone must not skip in-process rescue when the consumer is broken."""
    monkeypatch.setattr(settings, "mq_enabled", True)
    monkeypatch.setattr(settings, "enable_stale_watchdog", True)

    dispatch = AsyncMock()
    with (
        patch("app.watchdog.db.list_stale_run_ids", new_callable=AsyncMock) as list_stale,
        patch("app.watchdog.orchestrator.run_is_active_locally", return_value=False),
        patch("app.watchdog.try_claim_run_dispatch", new_callable=AsyncMock, return_value=True),
        patch("app.watchdog.publish_run_if_mq", new_callable=AsyncMock) as publish,
        patch("app.watchdog.asyncio.create_task") as create_task,
        patch("app.watchdog.orchestrator.dispatch_run_execute", dispatch),
        patch("app.watchdog.db.reap_stale_work", new_callable=AsyncMock, return_value={}),
    ):
        list_stale.return_value = ["run-stuck"]
        await tick_stale_run_watchdog()

    publish.assert_awaited_once_with("run-stuck")
    dispatch.assert_called_once_with("run-stuck")
    create_task.assert_called_once()
