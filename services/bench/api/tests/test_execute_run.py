"""Tests for MQ execute_run idempotency."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from bench_common.core.run import Episode, Run, RunConfig
from bench_common.orchestrator import service as orchestrator


@pytest.mark.asyncio
async def test_execute_run_skips_terminal_run() -> None:
    run = Run(
        id="run-1",
        config=RunConfig(
            domain_id="d1",
            binding_vow_version="1.0.0",
            agent_config={"model": "openai/gpt-4o"},
        ),
        requester_id="u1",
        status="completed",
    )

    with patch.object(orchestrator.db, "get_run", new_callable=AsyncMock) as get_run:
        get_run.return_value = run
        await orchestrator.execute_run("run-1")

    get_run.assert_called_once_with("run-1")


@pytest.mark.asyncio
async def test_execute_run_skips_when_no_pending_episodes() -> None:
    run = Run(
        id="run-2",
        config=RunConfig(
            domain_id="d1",
            binding_vow_version="1.0.0",
            agent_config={"model": "openai/gpt-4o"},
        ),
        requester_id="u1",
        status="running",
    )
    episodes = [Episode(id="ep-1", run_id="run-2", status="completed")]

    with (
        patch.object(orchestrator.db, "get_run", new_callable=AsyncMock) as get_run,
        patch.object(orchestrator.db, "get_episodes", new_callable=AsyncMock) as get_episodes,
        patch.object(orchestrator, "_run_all_episodes", new_callable=AsyncMock) as run_all,
    ):
        get_run.return_value = run
        get_episodes.return_value = episodes
        await orchestrator.execute_run("run-2")

    run_all.assert_not_called()


@pytest.mark.asyncio
async def test_create_run_publishes_when_mq_enabled(monkeypatch) -> None:
    monkeypatch.setattr(orchestrator.settings, "mq_enabled", True)
    publish = AsyncMock()
    monkeypatch.setattr(orchestrator, "publish_run_if_mq", publish)

    domain = AsyncMock()
    domain.binding_vow.version = "1.0.0"
    domain.binding_vow.techniques = []
    domain.id = "d1"

    with (
        patch.object(orchestrator.db, "get_domain", new_callable=AsyncMock) as get_domain,
        patch.object(orchestrator.db, "save_run", new_callable=AsyncMock),
        patch.object(orchestrator.db, "save_episode", new_callable=AsyncMock),
        patch.object(orchestrator, "_schedule_run_execution") as schedule,
    ):
        get_domain.return_value = domain
        config = RunConfig(
            domain_id="d1",
            binding_vow_version="1.0.0",
            agent_config={"model": "openai/gpt-4o"},
            num_episodes=1,
        )
        await orchestrator.create_run(config, requester_id="u1")

    publish.assert_awaited_once()
    schedule.assert_not_called()
