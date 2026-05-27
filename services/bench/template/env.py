"""
Your environment — replace this with your actual benchmark logic.

The only two methods you MUST implement are reset() and step().
Everything else has a sensible default in BaseEnv.

Quick reference
---------------
reset(seed, **params) -> observation
    Called once per episode. Return whatever the agent should see first
    (a dict, a string, a number — anything JSON-serializable).

step(action) -> StepResult(observation, reward, terminated, truncated, info)
    Called on every agent turn. Return:
      - observation  what the agent sees next (same type as reset)
      - reward       float, typically 0.0 or 1.0 for simple tasks
      - terminated   True when the episode is done (success or failure)
      - truncated    True when an episode limit was hit (not natural end)
      - info         dict[str, str]  — values MUST be strings

info dict gotcha: all values must be strings, e.g. str(True) not True.

parse_action(action) -> action  [optional, default: identity]
    The platform uses structured model outputs when possible — the model
    always returns exactly what your action_space schema describes.
    Override parse_action() only when your step() logic needs a different
    representation than the schema you expose to the model.

    Example: schema is {"type": "string", "enum": ["left","right","up","down"]}
    but step() wants integer directions::

        def parse_action(self, action):
            return {"left": 0, "right": 1, "up": 2, "down": 3}[action]

    Example: schema returns a dict but step() needs a tuple::

        def parse_action(self, action):
            return (action["x"], action["y"])
"""

from __future__ import annotations

import random
from typing import Any

from bench_common.env_sdk.base import BaseEnv, StepResult

# ── Replace with your benchmark data ─────────────────────────────────────────

ITEMS = [
    {"question": "What is 2 + 2?", "answer": "4"},
    {"question": "What color is the sky?", "answer": "blue"},
    {"question": "How many sides does a triangle have?", "answer": "3"},
]


class MyEnv(BaseEnv):
    """
    Template environment — one question per episode, text answer expected.
    Replace ITEMS and the scoring logic in step() with your own benchmark.
    """

    def __init__(self) -> None:
        self._item: dict[str, Any] | None = None
        self._rng = random.Random()

    # ── Called once at the start of every episode ──────────────────────────────
    def reset(self, seed: int | None = None, **params: Any) -> dict[str, Any]:
        self._rng.seed(seed)
        self._item = self._rng.choice(ITEMS)

        # Return only what the agent should see (hide the answer!)
        return {"question": self._item["question"]}

    # ── Called on every agent turn ─────────────────────────────────────────────
    def step(self, action: Any) -> StepResult:
        if self._item is None:
            raise RuntimeError("Call reset() before step()")

        response = str(action).strip().lower()
        correct = response == self._item["answer"].lower()

        return StepResult(
            observation={"result": "done"},
            reward=1.0 if correct else 0.0,
            terminated=True,  # set False for multi-turn episodes
            truncated=False,
            info={
                "correct": str(correct),  # must be str!
                "given_answer": response,
                "correct_answer": self._item["answer"],
            },
        )
