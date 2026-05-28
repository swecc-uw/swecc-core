from __future__ import annotations

from pathlib import Path
from subprocess import TimeoutExpired

import pytest


def test_resolve_repo_file_rejects_worker_path_traversal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("WORKER_API_URL", "http://localhost:8000")
    from app.worker import _resolve_repo_file

    outside = tmp_path.parent / "worker_outside_adapter.py"
    outside.write_text("print('bad')", encoding="utf-8")

    with pytest.raises(RuntimeError, match="inside the manifest directory"):
        _resolve_repo_file(tmp_path, "../worker_outside_adapter.py", "Adapter")


def test_resolve_repo_file_accepts_worker_nested_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("WORKER_API_URL", "http://localhost:8000")
    from app.worker import _resolve_repo_file

    adapter = tmp_path / "nested" / "adapter.py"
    adapter.parent.mkdir()
    adapter.write_text("print('ok')", encoding="utf-8")

    assert _resolve_repo_file(tmp_path, "nested/adapter.py", "Adapter") == adapter.resolve()


@pytest.mark.asyncio
async def test_clone_repo_times_out_with_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("WORKER_API_URL", "http://localhost:8000")
    from app import worker

    def _timeout(*args, **kwargs):
        raise TimeoutExpired(cmd="git clone", timeout=1)

    monkeypatch.setattr(worker, "GIT_CLONE_TIMEOUT", 1)
    monkeypatch.setattr(worker, "subprocess_run", _timeout)

    with pytest.raises(RuntimeError, match="git clone exceeded 1s timeout"):
        await worker._clone_repo("https://github.com/swecc/example", tmp_path)
