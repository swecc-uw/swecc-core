"""
Episodic memory technique.

Maintains a sliding window of the most recent (observation, action, reward)
triples and prepends them to the agent's context on each step.

When the window is full and older entries start being dropped, a header is
prepended that says exactly which steps are no longer shown.  The window does
NOT summarise or compress the kept entries — it is a verbatim history of the
last ``window_size`` steps.

If you need lossy compression (e.g. to stay within context limits on very long
episodes), implement it inside your env's observation: build a summary into the
dict you return from step() and your env controls what the model remembers.

Configuration keys (passed via TechniqueDeclaration.config_schema):
    window_size  int  Number of most-recent steps to include (default: 10).
"""

from __future__ import annotations

import json
import logging
from collections import deque
from typing import Any

from bench_common.core.binding_vow import TechniqueDeclaration
from bench_common.techniques.base import Technique

log = logging.getLogger(__name__)


class EpisodicMemoryTechnique(Technique):
    def __init__(self) -> None:
        self._window: deque[dict[str, Any]] = deque()
        self._window_size: int = 10
        self._dropped_summary: str = ""
        self._step_counter: int = 0

    def id(self) -> str:
        return "memory"

    def compatible(self, declaration: TechniqueDeclaration) -> bool:
        return declaration.technique_id == self.id()

    async def on_episode_start(self, episode_id: str, config: dict[str, Any]) -> None:
        self._window_size = int(config.get("window_size", 10))
        if "summarize_after" in config:
            log.warning(
                "EpisodicMemoryTechnique: 'summarize_after' config key is no longer used. "
                "The technique shows the last 'window_size' steps verbatim; older steps are "
                "dropped automatically when the window is full.  Remove 'summarize_after' "
                "from your technique config."
            )
        self._window = deque(maxlen=self._window_size)
        self._dropped_summary = ""
        self._step_counter = 0

    async def before_action(
        self,
        observation: Any,
        agent_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._window:
            return {}
        history_lines: list[str] = []
        if self._dropped_summary:
            history_lines.append(self._dropped_summary)
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
        # Once the window is full and old steps are being dropped, show a header
        # that is honest about what the model is not seeing.
        if self._step_counter > self._window_size:
            dropped_through = self._step_counter - self._window_size
            self._dropped_summary = (
                f"[Steps 1–{dropped_through} are not shown; "
                f"displaying the {self._window_size} most recent steps only.]"
            )

    async def on_episode_end(self, episode_id: str, terminal_info: dict[str, Any]) -> None:
        self._window.clear()
        self._dropped_summary = ""
        self._step_counter = 0
