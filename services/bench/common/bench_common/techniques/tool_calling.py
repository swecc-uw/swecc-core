"""
Tool-calling technique.

Injects available tool definitions into the system prompt and dispatches
tool calls parsed from model responses back through the environment's
/tool endpoint (if the environment supports it).

For now this is a pass-through — the domain's technique config defines
available tools; the model sees them as part of the context.
"""

from __future__ import annotations

import json
from typing import Any

from bench_common.core.binding_vow import TechniqueDeclaration
from bench_common.techniques.base import Technique


class ToolCallingTechnique(Technique):
    def __init__(self) -> None:
        self._tools: list[dict[str, Any]] = []

    def id(self) -> str:
        return "tool_calling"

    def compatible(self, declaration: TechniqueDeclaration) -> bool:
        return declaration.technique_id == self.id()

    async def on_episode_start(self, episode_id: str, config: dict[str, Any]) -> None:
        self._tools = config.get("tools", [])

    async def before_action(
        self,
        observation: Any,
        agent_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._tools:
            return {}
        tools_text = json.dumps(self._tools, indent=2)
        return {"Available Tools": f"```json\n{tools_text}\n```"}

    async def after_action(
        self,
        action: Any,
        step_result: Any,
        agent_state: dict[str, Any],
    ) -> None:
        pass

    async def on_episode_end(self, episode_id: str, terminal_info: dict[str, Any]) -> None:
        self._tools = []
