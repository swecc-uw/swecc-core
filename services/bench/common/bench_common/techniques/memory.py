"""
Episodic memory technique.

Maintains a sliding window of recent (observation, action, reward) triples.
When the window exceeds `summarize_after` entries a brief summary string
is prepended so the model stays within context limits.
"""
from __future__ import annotations

import json
from collections import deque
from typing import Any

from bench_common.core.binding_vow import TechniqueDeclaration
from bench_common.techniques.base import Technique


class EpisodicMemoryTechnique(Technique):
    def __init__(self) -> None:
        self._window: deque[dict[str, Any]] = deque()
        self._window_size: int = 10
        self._summarize_after: int = 5
        self._summary: str = ""
        self._step_counter: int = 0

    def id(self) -> str:
        return "memory"

    def compatible(self, declaration: TechniqueDeclaration) -> bool:
        return declaration.technique_id == self.id()

    async def on_episode_start(
        self, episode_id: str, config: dict[str, Any]
    ) -> None:
        self._window_size = int(config.get("window_size", 10))
        self._summarize_after = int(config.get("summarize_after", 5))
        self._window = deque(maxlen=self._window_size)
        self._summary = ""
        self._step_counter = 0

    async def before_action(
        self,
        observation: Any,
        agent_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._window:
            return {}
        history_lines: list[str] = []
        if self._summary:
            history_lines.append(f"[Earlier summary] {self._summary}")
        for entry in self._window:
            obs_str = (
                json.dumps(entry["obs"])
                if isinstance(entry["obs"], (dict, list))
                else str(entry["obs"])
            )
            history_lines.append(
                f"Step {entry['step']}: obs={obs_str[:120]} | "
                f"action={entry['action']} | reward={entry['reward']}"
            )
        return {"Recent History": "\n".join(history_lines)}

    async def after_action(
        self,
        action: Any,
        step_result: Any,
        agent_state: dict[str, Any],
    ) -> None:
        self._step_counter += 1
        self._window.append(
            {
                "step": self._step_counter,
                "obs": getattr(step_result.observation, "data", str(step_result.observation)),
                "action": action,
                "reward": step_result.reward,
            }
        )
        # Naive summarisation: just keep a running count
        if len(self._window) >= self._summarize_after:
            total_reward = sum(e["reward"] for e in self._window)
            self._summary = (
                f"{len(self._window)} steps so far, "
                f"cumulative reward={total_reward:.3f}"
            )

    async def on_episode_end(
        self, episode_id: str, terminal_info: dict[str, Any]
    ) -> None:
        self._window.clear()
        self._summary = ""
        self._step_counter = 0
