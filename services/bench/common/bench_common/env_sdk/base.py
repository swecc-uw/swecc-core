"""
BaseEnv — the abstract class every environment adapter must implement.

The interface mirrors Gymnasium's (reset / step / close) so that wrapping
an existing Gym env requires almost no code.  The platform calls these methods
via the HTTP adapter server in src/env_sdk/server.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepResult:
    """Return value of BaseEnv.step()."""
    observation: Any
    reward: float
    terminated: bool
    truncated: bool
    info: dict[str, Any] = field(default_factory=dict)
    system_prompt: str | None = None  # optional override for the next inference step


class BaseEnv(ABC):
    """
    Subclass this and implement reset() + step().
    close() and render() are optional.

    Episode lifecycle (called by the adapter server):
        env = MyEnv()
        obs  = env.reset(seed=42)
        while True:
            result = env.step(action)
            if result.terminated or result.truncated:
                break
        env.close()

    Each episode gets its own env instance, so you don't need to worry
    about concurrent episodes sharing state.
    """

    @abstractmethod
    def reset(self, seed: int | None = None, **params: Any) -> Any:
        """
        Reset the environment and return the initial observation.

        Args:
            seed:   Optional RNG seed for reproducibility.
            params: Arbitrary scenario parameters from the RunConfig.

        Returns:
            The initial observation.  Can be any JSON-serialisable value
            (dict, list, str, int, float).
        """
        ...

    @abstractmethod
    def step(self, action: Any) -> StepResult:
        """
        Execute one step in the environment.

        Args:
            action: The action chosen by the agent.  Matches the Domain's
                    action_space definition in the Binding Vow.

        Returns:
            StepResult(observation, reward, terminated, truncated, info)
            - observation: next observation (JSON-serialisable)
            - reward:      float reward signal
            - terminated:  True if the episode ended naturally (goal / fail)
            - truncated:   True if cut short by a time/step limit
            - info:        dict[str, str] — extra metadata for traces
        """
        ...

    def close(self) -> None:
        """Release resources.  Called after every episode.  Override if needed."""
        pass

    def render(self, mode: str = "text") -> Any:
        """
        Optional: return a human-readable snapshot for replay / debugging.

        Args:
            mode: "text", "rgb_array", or "html"

        Returns:
            str | bytes | dict — whatever makes sense for your env.
        """
        return {}
