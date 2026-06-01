from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import app.manager as manager
import pytest
from bench_common.core.errors import EnvironmentStartupError


@pytest.fixture(autouse=True)
def reset_manager_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(manager, "_registry", {})
    monkeypatch.setattr(manager, "_env_clone_locks", {})
    monkeypatch.setattr(
        manager,
        "_available_ports",
        set(range(manager._PORT_RANGE_START, manager._PORT_RANGE_START + 10)),
    )


def test_running_clone_result_none_when_missing() -> None:
    assert manager._running_clone_result("missing-env") is None


def test_running_clone_result_none_when_not_running() -> None:
    manager._registry["env-1"] = {
        "process": SimpleNamespace(returncode=None),
        "port": 9001,
        "manifest": {"name": "demo"},
        "status": "starting",
    }
    assert manager._running_clone_result("env-1") is None


def test_running_clone_result_none_when_process_exited() -> None:
    manager._registry["env-1"] = {
        "process": SimpleNamespace(returncode=1),
        "port": 9001,
        "manifest": {"name": "demo"},
        "status": "running",
    }
    assert manager._running_clone_result("env-1") is None


def test_running_clone_result_returns_payload_when_running() -> None:
    manifest = {"name": "demo"}
    manager._registry["env-1"] = {
        "process": SimpleNamespace(returncode=None),
        "port": 9001,
        "manifest": manifest,
        "status": "running",
    }

    assert manager._running_clone_result("env-1") == {
        "env_id": "env-1",
        "url": "http://localhost:9001",
        "manifest": manifest,
    }


@pytest.mark.asyncio
async def test_env_clone_lock_reuses_lock_for_same_env_id() -> None:
    lock_a = await manager._env_clone_lock("same-env")
    lock_b = await manager._env_clone_lock("same-env")
    assert lock_a is lock_b


@pytest.mark.asyncio
async def test_clone_and_start_skips_when_env_already_running() -> None:
    manifest = {"name": "demo"}
    manager._registry["env-1"] = {
        "process": SimpleNamespace(returncode=None),
        "port": 9002,
        "manifest": manifest,
        "status": "running",
    }

    with patch(
        "app.manager.asyncio.create_subprocess_exec", new=AsyncMock()
    ) as mock_exec:
        result = await manager.clone_and_start("env-1", "https://github.com/o/r")

    assert result == {
        "env_id": "env-1",
        "url": "http://localhost:9002",
        "manifest": manifest,
    }
    mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_clone_and_start_serializes_same_env_id() -> None:
    active_clones = 0
    max_active_clones = 0
    clone_started = asyncio.Event()
    release_clone = asyncio.Event()

    async def fake_create_subprocess_exec(*args, **kwargs):
        nonlocal active_clones, max_active_clones
        if args[:2] == ("git", "clone"):
            active_clones += 1
            max_active_clones = max(max_active_clones, active_clones)
            clone_started.set()
            await release_clone.wait()
            active_clones -= 1
            return SimpleNamespace(
                communicate=AsyncMock(return_value=(b"", b"")),
                returncode=1,
                kill=lambda: None,
                wait=AsyncMock(return_value=0),
                pid=123,
            )
        raise AssertionError(f"unexpected subprocess: {args}")

    with patch(
        "app.manager.asyncio.create_subprocess_exec",
        side_effect=fake_create_subprocess_exec,
    ):
        task_a = asyncio.create_task(
            manager.clone_and_start("env-1", "https://github.com/o/r")
        )
        task_b = asyncio.create_task(
            manager.clone_and_start("env-1", "https://github.com/o/r")
        )

        await asyncio.wait_for(clone_started.wait(), timeout=1.0)
        await asyncio.sleep(0.05)
        assert active_clones == 1
        release_clone.set()

        results = await asyncio.gather(task_a, task_b, return_exceptions=True)

    assert max_active_clones == 1
    assert all(isinstance(result, EnvironmentStartupError) for result in results)
