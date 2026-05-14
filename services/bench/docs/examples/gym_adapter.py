"""
Gymnasium adapter — wrap any existing Gym env in two classes.

This shows how an env developer who already has a Gymnasium environment
can publish it on BenchAnything without rewriting their env logic.

Requirements:
    pip install gymnasium   (or it's already in your project)

Usage:
    1. Replace `gymnasium.make("CartPole-v1")` with your own env.
    2. Fill in the DomainConfig in the __main__ block.
    3. Run: uv run python docs/examples/gym_adapter.py
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from typing import Any

from bench_common.env_sdk.base import BaseEnv, StepResult


class GymEnvAdapter(BaseEnv):
    """
    Generic adapter for any Gymnasium-compatible environment.

    Usage:
        class CartPoleEnv(GymEnvAdapter):
            def _make_gym_env(self):
                import gymnasium
                return gymnasium.make("CartPole-v1")

    Or use the factory function below for a one-liner.
    """

    def _make_gym_env(self) -> Any:
        raise NotImplementedError("Override _make_gym_env() to return your Gym env")

    def __init__(self) -> None:
        self._env: Any = None

    def reset(self, seed: int | None = None, **params: Any) -> Any:
        if self._env is None:
            self._env = self._make_gym_env()
        obs, _info = self._env.reset(seed=seed)
        # Convert numpy arrays to plain lists for JSON serialisation
        return _to_json(obs)

    def step(self, action: Any) -> StepResult:
        if self._env is None:
            raise RuntimeError("Call reset() before step()")
        obs, reward, terminated, truncated, info = self._env.step(action)
        return StepResult(
            observation=_to_json(obs),
            reward=float(reward),
            terminated=bool(terminated),
            truncated=bool(truncated),
            info={str(k): str(v) for k, v in info.items()},
        )

    def close(self) -> None:
        if self._env is not None:
            self._env.close()
            self._env = None

    def render(self, mode: str = "text") -> Any:
        if self._env is None:
            return {}
        try:
            return _to_json(self._env.render())
        except Exception:
            return {}


def gym_adapter(gym_env_id: str, **gym_kwargs: Any) -> type[GymEnvAdapter]:
    """
    One-liner factory.  Returns a BaseEnv subclass backed by the given Gym env.

    Example:
        CartPole = gym_adapter("CartPole-v1")
        serve(CartPole, port=8765)
    """
    import gymnasium

    class _Adapter(GymEnvAdapter):
        def _make_gym_env(self) -> Any:
            return gymnasium.make(gym_env_id, **gym_kwargs)

    _Adapter.__name__ = gym_env_id.replace("/", "_").replace("-", "_")
    return _Adapter


def _to_json(value: Any) -> Any:
    """Recursively convert numpy types to plain Python for JSON serialisation."""
    try:
        import numpy as np
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
    except ImportError:
        pass
    if isinstance(value, dict):
        return {str(k): _to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json(v) for v in value]
    return value


# ── Example: run CartPole directly ───────────────────────────────────────────

if __name__ == "__main__":
    # Quick unit test — no server, no platform needed
    try:
        import gymnasium  # noqa: F401
    except ImportError:
        print("Install gymnasium first:  pip install gymnasium")
        sys.exit(1)

    CartPole = gym_adapter("CartPole-v1")
    env = CartPole()

    obs = env.reset(seed=42)
    print("Initial observation:", obs)

    for step in range(5):
        result = env.step(env._env.action_space.sample())
        print(
            f"Step {step+1}: reward={result.reward:.1f}  "
            f"terminated={result.terminated}  obs={result.observation}"
        )
        if result.terminated or result.truncated:
            break

    env.close()
    print("\nDone. To serve CartPole on the platform:")
    print("  from docs.examples.gym_adapter import gym_adapter")
    print("  from bench_common.env_sdk import serve")
    print('  serve(gym_adapter("CartPole-v1"), port=8765)')
