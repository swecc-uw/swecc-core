"""
Local filesystem trace store.
Each episode gets its own JSONL file: {trace_dir}/{episode_id}.jsonl
Each line is a serialized TraceEvent.
"""

from __future__ import annotations

import os
from pathlib import Path

import aiofiles
from bench_common.config import settings
from bench_common.core.run import TraceEvent


class TraceStore:
    def __init__(self, trace_dir: str | None = None) -> None:
        self._dir = Path(trace_dir or settings.trace_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, episode_id: str) -> Path:
        return self._dir / f"{episode_id}.jsonl"

    async def append(self, event: TraceEvent) -> None:
        async with aiofiles.open(self._path(event.episode_id), "a") as f:
            await f.write(event.model_dump_json() + "\n")

    async def read(self, episode_id: str) -> list[TraceEvent]:
        path = self._path(episode_id)
        if not path.exists():
            return []
        events: list[TraceEvent] = []
        async with aiofiles.open(path, "r") as f:
            async for line in f:
                line = line.strip()
                if line:
                    events.append(TraceEvent.model_validate_json(line))
        return events

    async def delete(self, episode_id: str) -> None:
        path = self._path(episode_id)
        if path.exists():
            path.unlink()


# Module-level singleton
trace_store = TraceStore()
