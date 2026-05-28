from __future__ import annotations

from pathlib import Path

import pytest
from app.manager import _resolve_repo_file
from bench_common.core.errors import ManifestError


def test_resolve_repo_file_accepts_nested_file_inside_repo(tmp_path: Path) -> None:
    adapter = tmp_path / "src" / "adapter.py"
    adapter.parent.mkdir()
    adapter.write_text("print('ok')", encoding="utf-8")

    assert _resolve_repo_file(tmp_path, "src/adapter.py", "Adapter") == adapter.resolve()


def test_resolve_repo_file_rejects_path_traversal(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_adapter.py"
    outside.write_text("print('bad')", encoding="utf-8")

    with pytest.raises(ManifestError, match="inside the repository root"):
        _resolve_repo_file(tmp_path, "../outside_adapter.py", "Adapter")


def test_resolve_repo_file_rejects_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="relative"):
        _resolve_repo_file(tmp_path, str(tmp_path / "adapter.py"), "Adapter")
