"""
Multi-agent technique (stub for MVP).

Manages named roles within an episode. In a full implementation each
role would use a separate AgentConfig and InferenceRouter. For now the
technique injects role metadata into the prompt so a single model can
simulate a given role.
"""

from __future__ import annotations

from typing import Any

from bench_common.core.binding_vow import TechniqueDeclaration
from bench_common.techniques.base import Technique


class MultiAgentTechnique(Technique):
    def __init__(self) -> None:
        self._roles: list[str] = []
        self._current_role: str = ""
        self._turn: int = 0

    def id(self) -> str:
        return "multi_agent"

    def compatible(self, declaration: TechniqueDeclaration) -> bool:
        return declaration.technique_id == self.id()

    async def on_episode_start(self, episode_id: str, config: dict[str, Any]) -> None:
        self._roles = config.get("roles", [])
        self._turn = 0
        self._current_role = self._roles[0] if self._roles else ""

    async def before_action(
        self,
        observation: Any,
        agent_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._current_role:
            return {}
        return {"Your Role": self._current_role}

    async def after_action(
        self,
        action: Any,
        step_result: Any,
        agent_state: dict[str, Any],
    ) -> None:
        if self._roles:
            self._turn += 1
            self._current_role = self._roles[self._turn % len(self._roles)]

    async def on_episode_end(self, episode_id: str, terminal_info: dict[str, Any]) -> None:
        self._roles = []
        self._current_role = ""
        self._turn = 0
