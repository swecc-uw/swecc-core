"""Tests for dispatch_run_execute error handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bench_common.orchestrator import service as orchestrator


@pytest.mark.asyncio
async def test_dispatch_run_execute_marks_failed_on_exception() -> None:
    with (
        patch.object(orchestrator, "execute_run", new_callable=AsyncMock) as execute,
        patch.object(orchestrator, "_fail_run", new_callable=AsyncMock) as fail_run,
    ):
        execute.side_effect = RuntimeError("boom")
        await orchestrator.dispatch_run_execute("run-1")

    fail_run.assert_awaited_once_with("run-1", "execute_run_error", detail="boom")
