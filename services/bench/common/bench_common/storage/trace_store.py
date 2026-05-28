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

    async def read_since(self, episode_id: str, *, offset: int) -> tuple[list[TraceEvent], int]:
        """Read trace events written since ``offset`` bytes; return (events, new_offset).

        Lets long-lived viewers (e.g. the WebSocket trace stream) avoid
        re-parsing the entire file on every tick — without this, a 1000-step
        episode becomes O(steps^2) Pydantic validations per viewer per second.

        ``offset`` of 0 reads from the start. A partial trailing line (we
        caught mid-write) is left for the next call by advancing only to the
        last newline boundary actually parsed.
        """
        path = self._path(episode_id)
        if not path.exists():
            return [], offset
        events: list[TraceEvent] = []
        bytes_consumed = offset
        async with aiofiles.open(path, "rb") as f:
            await f.seek(offset)
            data = await f.read()
        if not data:
            return [], offset
        # Split on newlines, but only keep complete lines. A trailing partial
        # line means a concurrent writer is mid-append; leave it for next call.
        text = data.decode("utf-8", errors="replace")
        last_newline = text.rfind("\n")
        if last_newline == -1:
            return [], offset
        complete = text[: last_newline + 1]
        for line in complete.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            events.append(TraceEvent.model_validate_json(stripped))
        bytes_consumed += len(complete.encode("utf-8"))
        return events, bytes_consumed

    async def delete(self, episode_id: str) -> None:
        path = self._path(episode_id)
        if path.exists():
            path.unlink()


# Module-level singleton
trace_store = TraceStore()
