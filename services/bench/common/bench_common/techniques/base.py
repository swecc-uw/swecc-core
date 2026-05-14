from abc import ABC, abstractmethod
from typing import Any

from bench_common.core.binding_vow import TechniqueDeclaration


class Technique(ABC):
    """Base interface all Techniques implement."""

    @abstractmethod
    def id(self) -> str: ...

    @abstractmethod
    def compatible(self, declaration: TechniqueDeclaration) -> bool:
        """Check if this implementation satisfies the domain's declaration."""
        ...

    @abstractmethod
    async def on_episode_start(self, episode_id: str, config: dict[str, Any]) -> None: ...

    @abstractmethod
    async def before_action(
        self,
        observation: Any,
        agent_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Inject context into the agent's decision prompt."""
        ...

    @abstractmethod
    async def after_action(
        self,
        action: Any,
        step_result: Any,
        agent_state: dict[str, Any],
    ) -> None:
        """Post-step bookkeeping."""
        ...

    @abstractmethod
    async def on_episode_end(self, episode_id: str, terminal_info: dict[str, Any]) -> None: ...
