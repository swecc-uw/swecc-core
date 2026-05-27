"""
Your benchmark logic — implement reset() and step().

Required: reset(), step()
Optional: parse_action(), close(), render()

parse_action(action) — override when your step() needs a different
representation than the JSON Schema you declare in benchanything.json.
The platform always delivers what the schema describes; use parse_action
to remap it before step() sees it.  Default is an identity (no-op).
"""

from __future__ import annotations

import random
from typing import Any

from bench_common.env_sdk.base import BaseEnv, StepResult

ITEMS = [
    {"question": "What is 2 + 2?", "answer": "4"},
    {"question": "What color is the sky?", "answer": "blue"},
]


class MyEnv(BaseEnv):
    def __init__(self) -> None:
        self._item: dict[str, Any] | None = None
        self._rng = random.Random()

    def reset(self, seed: int | None = None, **params: Any) -> dict[str, Any]:
        self._rng.seed(seed)
        self._item = self._rng.choice(ITEMS)
        return {"question": self._item["question"]}

    # ── Optional: remap the structured action before step() sees it ───────────
    # def parse_action(self, action: Any) -> Any:
    #     # Example: schema enum → int
    #     return {"left": 0, "right": 1, "up": 2, "down": 3}[action]

    def step(self, action: Any) -> StepResult:
        if self._item is None:
            raise RuntimeError("Call reset() before step()")
        response = str(action).strip().lower()
        correct = response == self._item["answer"].lower()
        return StepResult(
            observation={"result": "done"},
            reward=1.0 if correct else 0.0,
            terminated=True,
            truncated=False,
            info={"correct": str(correct), "given_answer": response},
        )
