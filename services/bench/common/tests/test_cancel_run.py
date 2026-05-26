"""Tests for run cancellation orchestration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bench_common.core.run import Episode, Run, RunConfig
from bench_common.orchestrator import service as orchestrator


@pytest.mark.asyncio
async def test_cancel_run_marks_pending_episodes_cancelled() -> None:
    run = Run(
        id="run-1",
        config=RunConfig(
            domain_id="d1",
            binding_vow_version="1.0.0",
            agent_config={"model": "openai/gpt-4o"},
        ),
        requester_id="u1",
        status="running",
    )
    episodes = [
        Episode(id="ep-1", run_id="run-1", status="pending"),
        Episode(id="ep-2", run_id="run-1", status="running"),
        Episode(id="ep-3", run_id="run-1", status="completed"),
    ]

    with (
        patch.object(orchestrator.db, "get_run", new_callable=AsyncMock) as get_run,
        patch.object(orchestrator.db, "save_run", new_callable=AsyncMock) as save_run,
        patch.object(orchestrator.db, "get_episodes", new_callable=AsyncMock) as get_episodes,
        patch.object(orchestrator.db, "save_episode", new_callable=AsyncMock) as save_episode,
    ):
        get_run.return_value = run
        get_episodes.return_value = episodes

        result = await orchestrator.cancel_run("run-1")

    assert result.status == "cancelled"
    assert save_run.await_count == 1
    assert save_episode.await_count == 2
    saved_statuses = [c.args[0].status for c in save_episode.await_args_list]
    assert saved_statuses == ["cancelled", "cancelled"]


@pytest.mark.asyncio
async def test_cancel_run_is_idempotent_when_already_terminal() -> None:
    run = Run(
        id="run-2",
        config=RunConfig(
            domain_id="d1",
            binding_vow_version="1.0.0",
            agent_config={"model": "openai/gpt-4o"},
        ),
        requester_id="u1",
        status="completed",
    )

    with (
        patch.object(orchestrator.db, "get_run", new_callable=AsyncMock) as get_run,
        patch.object(orchestrator.db, "save_run", new_callable=AsyncMock) as save_run,
    ):
        get_run.return_value = run
        result = await orchestrator.cancel_run("run-2")

    assert result.status == "completed"
    save_run.assert_not_awaited()
