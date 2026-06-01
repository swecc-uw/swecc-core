"""
Arithmetic benchmark environment.

Generates 10 math problems per episode covering all four operations
(addition, subtraction, multiplication, integer division).
Division problems are constructed to always have whole-number answers.
"""

from __future__ import annotations

import random
from typing import Any

from bench_common.env_sdk.base import BaseEnv, StepResult

PROBLEMS_PER_EPISODE = 10
_OPS = ["+", "-", "*", "/"]


def _generate_problem(op: str, rng: random.Random) -> tuple[str, int]:
    if op == "+":
        a, b = rng.randint(1, 50), rng.randint(1, 50)
        return f"{a} + {b}", a + b
    elif op == "-":
        a = rng.randint(10, 100)
        b = rng.randint(1, a)
        return f"{a} - {b}", a - b
    elif op == "*":
        a, b = rng.randint(2, 12), rng.randint(2, 12)
        return f"{a} * {b}", a * b
    else:  # "/"
        divisor = rng.randint(2, 12)
        quotient = rng.randint(2, 12)
        dividend = divisor * quotient
        return f"{dividend} / {divisor}", quotient


class ArithmeticEnv(BaseEnv):
    """
    10-step episode: one arithmetic problem per step.
    Observation: { "problem": "12 + 7", "problem_num": 1, "total_problems": 10 }
    Action:      { "answer": 19 }
    Reward:      1.0 per correct answer, 0.0 otherwise.
    """

    def __init__(self) -> None:
        self._problems: list[tuple[str, int]] = []
        self._step_idx: int = 0
        self._correct: int = 0

    def reset(self, seed: int | None = None, **params: Any) -> dict[str, Any]:
        rng = random.Random(seed)
        # Ensure all 4 operations appear, distribute remainder randomly
        ops = _OPS * (PROBLEMS_PER_EPISODE // 4) + rng.sample(
            _OPS, PROBLEMS_PER_EPISODE % 4
        )
        rng.shuffle(ops)
        self._problems = [_generate_problem(op, rng) for op in ops]
        self._step_idx = 0
        self._correct = 0
        problem_text, _ = self._problems[0]
        return {
            "problem": problem_text,
            "problem_num": 1,
            "total_problems": PROBLEMS_PER_EPISODE,
        }

    def step(self, action: Any) -> StepResult:
        _, expected = self._problems[self._step_idx]

        try:
            given = int(round(float(action["answer"])))
        except (KeyError, TypeError, ValueError):
            given = None

        is_correct = given == expected
        if is_correct:
            self._correct += 1

        self._step_idx += 1
        terminated = self._step_idx >= PROBLEMS_PER_EPISODE

        if terminated:
            next_obs: dict[str, Any] = {
                "result": "done",
                "score": f"{self._correct}/{PROBLEMS_PER_EPISODE}",
            }
        else:
            next_problem_text, _ = self._problems[self._step_idx]
            next_obs = {
                "problem": next_problem_text,
                "problem_num": self._step_idx + 1,
                "total_problems": PROBLEMS_PER_EPISODE,
            }

        return StepResult(
            observation=next_obs,
            reward=1.0 if is_correct else 0.0,
            terminated=terminated,
            truncated=False,
            info={
                "correct": str(is_correct),
                "expected": str(expected),
                "given": str(given),
                "problems_correct_so_far": str(self._correct),
            },
        )
