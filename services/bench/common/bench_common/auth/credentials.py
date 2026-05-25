"""Local CLI credential store (not persisted to any database)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

DEFAULT_CREDENTIALS_PATH = Path.home() / ".config" / "swecc" / "bench_credentials.json"

Mode = Literal["member", "guest"]


def credentials_path() -> Path:
    return Path(os.environ.get("SWECC_BENCH_CREDENTIALS", str(DEFAULT_CREDENTIALS_PATH)))


def load_credentials() -> dict[str, Any] | None:
    path = credentials_path()
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_credentials(data: dict[str, Any]) -> None:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def clear_credentials() -> None:
    path = credentials_path()
    if path.exists():
        path.unlink()
