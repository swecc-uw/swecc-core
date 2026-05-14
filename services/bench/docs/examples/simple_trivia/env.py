"""
Simple trivia quiz environment.

This is a complete, working example of a BenchAnything environment.
Replace the QUESTIONS list and scoring logic with your own benchmark.
"""
from __future__ import annotations

import random
from typing import Any

from bench_common.env_sdk.base import BaseEnv, StepResult

QUESTIONS = [
    {
        "question": "What is the capital of France?",
        "choices": {"A": "Berlin", "B": "Paris", "C": "Rome", "D": "Madrid"},
        "answer": "B",
    },
    {
        "question": "Which planet is closest to the Sun?",
        "choices": {"A": "Venus", "B": "Earth", "C": "Mercury", "D": "Mars"},
        "answer": "C",
    },
    {
        "question": "What is 7 × 8?",
        "choices": {"A": "54", "B": "56", "C": "58", "D": "64"},
        "answer": "B",
    },
    {
        "question": "Who wrote 'Romeo and Juliet'?",
        "choices": {"A": "Dickens", "B": "Austen", "C": "Shakespeare", "D": "Chaucer"},
        "answer": "C",
    },
    {
        "question": "What is the chemical symbol for gold?",
        "choices": {"A": "Go", "B": "Gd", "C": "Ag", "D": "Au"},
        "answer": "D",
    },
]


class SimpleTriviaEnv(BaseEnv):
    """
    One question per episode.  The agent receives a multiple-choice question
    and must respond with a single letter (A/B/C/D).

    Reward: 1.0 for the correct answer, 0.0 otherwise.
    Episodes are always 1 step long.
    """

    def __init__(self) -> None:
        self._question: dict[str, Any] | None = None
        self._rng = random.Random()

    def reset(self, seed: int | None = None, **params: Any) -> dict[str, Any]:
        self._rng.seed(seed)
        idx = self._rng.randint(0, len(QUESTIONS) - 1)
        self._question = QUESTIONS[idx]

        # Return only what the agent should see — keep the answer hidden
        return {
            "question": self._question["question"],
            "choices": self._question["choices"],
        }

    def step(self, action: Any) -> StepResult:
        if self._question is None:
            raise RuntimeError("Call reset() before step()")

        answer = str(action).strip().upper()
        correct = answer == self._question["answer"]

        return StepResult(
            observation={"result": "done"},
            reward=1.0 if correct else 0.0,
            terminated=True,   # single-step episode
            truncated=False,
            info={
                "correct": str(correct),
                "given_answer": answer,
                "correct_answer": self._question["answer"],
            },
        )

    def render(self, mode: str = "text") -> str:
        if self._question is None:
            return "(no active question)"
        q = self._question
        return (
            f"Q: {q['question']}\n"
            + "\n".join(f"  {k}: {v}" for k, v in q["choices"].items())
        )
