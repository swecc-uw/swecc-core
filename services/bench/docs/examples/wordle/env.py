"""
Wordle environment.

6 tries to guess a 5-letter word. After each guess the agent receives
per-letter feedback: "green" (correct letter, correct position),
"yellow" (correct letter, wrong position), "gray" (not in the word).
"""
from __future__ import annotations

import os
import random
from typing import Any

from bench_common.env_sdk.base import BaseEnv, StepResult


class WordleEnv(BaseEnv):
    """6 tries to guess a 5-letter word."""

    def __init__(self) -> None:
        self._secret: str | None = None
        self._guesses_used: int = 0
        self._max_guesses: int = 6
        self._rng = random.Random()

        words_path = os.path.join(os.path.dirname(__file__), "words.txt")
        with open(words_path) as f:
            self._valid_words = [w.strip().lower() for w in f if w.strip()]

    def reset(self, seed: int | None = None, **params: Any) -> dict[str, Any]:
        self._rng.seed(seed)
        self._secret = self._rng.choice(self._valid_words)
        self._guesses_used = 0

        return {
            "instructions": "Guess the 5-letter word. You have 6 tries.",
            "guesses_so_far": [],
            "guesses_remaining": self._max_guesses,
        }

    def step(self, action: Any) -> StepResult:
        if self._secret is None:
            raise RuntimeError("Call reset() before step()")

        guess = str(action).strip().lower()
        self._guesses_used += 1

        if len(guess) != 5 or guess not in self._valid_words:
            return StepResult(
                observation={
                    "error": "invalid guess",
                    "guesses_remaining": self._max_guesses - self._guesses_used,
                },
                reward=0.0,
                terminated=False,
                truncated=False,
                info={"valid": "False", "guess": guess},
            )

        feedback = self._score_guess(guess, self._secret)
        won = guess == self._secret
        out_of_guesses = self._guesses_used >= self._max_guesses

        reward = 1.0 if won else 0.0
        terminated = won or out_of_guesses

        return StepResult(
            observation={
                "last_guess": guess,
                "feedback": feedback,
                "guesses_remaining": self._max_guesses - self._guesses_used,
            },
            reward=reward,
            terminated=terminated,
            truncated=False,
            info={
                "won": str(won),
                "guess": guess,
                "secret": self._secret if terminated else "",
                "guesses_used": str(self._guesses_used),
            },
        )

    def _score_guess(self, guess: str, secret: str) -> list[str]:
        result = ["gray"] * 5
        secret_chars = list(secret)

        for i in range(5):
            if guess[i] == secret_chars[i]:
                result[i] = "green"
                secret_chars[i] = ""

        for i in range(5):
            if result[i] == "green":
                continue
            if guess[i] in secret_chars:
                result[i] = "yellow"
                secret_chars[secret_chars.index(guess[i])] = ""

        return result

    def render(self, mode: str = "text") -> str:
        return (
            f"secret={'*' * 5} "
            f"guesses_used={self._guesses_used}/{self._max_guesses}"
        )
