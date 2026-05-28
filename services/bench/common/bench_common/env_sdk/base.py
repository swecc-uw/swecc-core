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
    # MIME type of ``observation``.  Defaults to JSON.  Set to "image/png",
    # "image/jpeg", etc. when returning raw image bytes or a base64 string so
    # the inference layer can build a proper vision-API message instead of
    # serialising the value as text.
    content_type: str = "application/json"


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

    def parse_action(self, action: Any) -> Any:
        """
        Optional: remap the structured action the platform delivers to whatever
        your ``step()`` method expects.

        The platform calls this automatically after extracting the action from
        the model's response (structured output or free-text parse).  The
        default implementation is an identity — ``step()`` receives the raw
        value.  Override when the schema the model fills in differs from the
        representation your step() logic uses.

        Example — the binding vow exposes ``{"type": "string", "enum": ["left",
        "right", "up", "down"]}`` but step() wants integers::

            def parse_action(self, action):
                return {"left": 0, "right": 1, "up": 2, "down": 3}[action]

        Args:
            action: The action value extracted from the model response.
                    Type depends on the action_space definition.

        Returns:
            The value to pass to ``step()``.
        """
        return action

    def close(self) -> None:  # noqa: B027 — intentional no-op default; subclasses may override
        """Release resources.  Called after every episode.  Override if needed."""

    def render(self, mode: str = "text") -> Any:
        """
        Optional: return a human-readable snapshot for replay / debugging.

        Args:
            mode: "text", "rgb_array", or "html"

        Returns:
            str | bytes | dict — whatever makes sense for your env.
        """
        return {}
