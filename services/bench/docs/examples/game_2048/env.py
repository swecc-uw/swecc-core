"""
2048 sliding-tile game for BenchAnything (4x4, merge by sliding).
"""

from __future__ import annotations

import copy
import random
from typing import Any

from bench_common.env_sdk.base import BaseEnv, StepResult

Size = 4
TARGET = 2048
INVALID_PENALTY = -0.1
MAX_CONSECUTIVE_INVALID = 5


def _merge_line_to_left(line: list[int]) -> tuple[list[int], int]:
    tiles = [x for x in line if x != 0]
    new: list[int] = []
    score = 0
    i = 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i + 1] and tiles[i] != 0:
            m = tiles[i] * 2
            new.append(m)
            score += m
            i += 2
        else:
            new.append(tiles[i])
            i += 1
    while len(new) < Size:
        new.append(0)
    return new[:Size], score


def _transpose(g: list[list[int]]) -> list[list[int]]:
    return [list(row) for row in zip(*g, strict=True)]


def _grids_equal(a: list[list[int]], b: list[list[int]]) -> bool:
    for r in range(Size):
        for c in range(Size):
            if a[r][c] != b[r][c]:
                return False
    return True


def _max_tile(grid: list[list[int]]) -> int:
    return max(max(row) for row in grid)


def _has_target_or_more(grid: list[list[int]], target: int = TARGET) -> bool:
    return any(cell >= target for row in grid for cell in row)


def _add_random_cell(rng: random.Random, grid: list[list[int]]) -> None:
    empty = [(r, c) for r in range(Size) for c in range(Size) if grid[r][c] == 0]
    if not empty:
        return
    r, c = rng.choice(empty)
    grid[r][c] = 2 if rng.random() < 0.9 else 4


def _new_grid() -> list[list[int]]:
    return [[0 for _ in range(Size)] for _ in range(Size)]


def _apply_move(grid: list[list[int]], name: str) -> tuple[list[list[int]], int, bool]:
    n = str(name).strip().lower()
    g = copy.deepcopy(grid)
    s = 0
    if n in ("l", "left"):
        new = []
        for r in range(Size):
            line, add = _merge_line_to_left(g[r])
            new.append(line)
            s += add
        return new, s, not _grids_equal(new, grid)
    if n in ("r", "right"):
        new = []
        for r in range(Size):
            line, add = _merge_line_to_left(list(reversed(g[r])))
            new.append(list(reversed(line)))
            s += add
        return new, s, not _grids_equal(new, grid)
    if n in ("u", "up"):
        t = _transpose(g)
        new = []
        for r in range(Size):
            line, add = _merge_line_to_left(t[r])
            new.append(line)
        out = _transpose(new)
        return out, s, not _grids_equal(out, grid)
    if n in ("d", "down"):
        t = _transpose(g)
        new = []
        for r in range(Size):
            line, add = _merge_line_to_left(list(reversed(t[r])))
            new.append(list(reversed(line)))
        out = _transpose(new)
        return out, s, not _grids_equal(out, grid)
    return g, 0, False


def _any_move_possible(grid: list[list[int]]) -> bool:
    for d in ("left", "right", "up", "down"):
        _, _, ch = _apply_move(grid, d)
        if ch:
            return True
    return False


def _action_norm(action: Any) -> str:
    a = str(action).strip().lower()
    one = {"w": "up", "s": "down", "a": "left", "z": "down"}
    return one.get(a, a)


class Game2048Env(BaseEnv):
    def __init__(self) -> None:
        self._rng: random.Random = random.Random()
        self._grid: list[list[int]] = _new_grid()
        self._score = 0
        self._step_index = 0
        self._max_episode_steps = 5_000
        self._consecutive_invalid = 0
        self._last_action_valid = True

    def reset(self, seed: int | None = None, **params: Any) -> dict[str, Any]:
        m = params.get("max_episode_steps")
        if isinstance(m, int) and m > 0:
            self._max_episode_steps = m
        self._rng.seed(seed)
        self._grid = _new_grid()
        self._score = 0
        self._step_index = 0
        self._consecutive_invalid = 0
        self._last_action_valid = True
        _add_random_cell(self._rng, self._grid)
        _add_random_cell(self._rng, self._grid)
        return self._obs()

    def _obs(self) -> dict[str, Any]:
        msg = f"4x4 2048. Actions: up, down, left, right. Win: reach tile {TARGET}."
        if not self._last_action_valid:
            msg += (
                f" WARNING: your last move was INVALID (no tiles moved)."
                f" Pick a DIFFERENT direction! ({self._consecutive_invalid}/{MAX_CONSECUTIVE_INVALID} strikes)"
            )
        return {
            "grid": self._grid,
            "score": self._score,
            "step": self._step_index,
            "target": TARGET,
            "size": Size,
            "message": msg,
        }

    def _info_metrics(self) -> dict[str, str]:
        hi = float(_max_tile(self._grid))
        won = 1.0 if _has_target_or_more(self._grid) else 0.0
        return {
            "max_tile": str(hi),
            "score": str(float(self._score)),
            "step": str(float(self._step_index)),
            "won": str(won),
        }

    def step(self, action: Any) -> StepResult:
        self._step_index += 1
        a = _action_norm(action)
        new_g, s_add, changed = _apply_move(self._grid, a)
        if not changed:
            self._consecutive_invalid += 1
            self._last_action_valid = False
            terminated = self._consecutive_invalid >= MAX_CONSECUTIVE_INVALID
            return StepResult(
                observation=self._obs(),
                reward=INVALID_PENALTY,
                terminated=terminated,
                truncated=False,
                info={**self._info_metrics(), "invalid": "1.0"},
            )

        self._consecutive_invalid = 0
        self._last_action_valid = True
        self._grid = new_g
        self._score += s_add
        reward = float(s_add) if s_add else 0.0
        _add_random_cell(self._rng, self._grid)

        won = _has_target_or_more(self._grid)
        dead = not _any_move_possible(self._grid)
        at_limit = self._step_index >= self._max_episode_steps
        if won:
            return StepResult(
                observation=self._obs(),
                reward=reward + 1_000.0,
                terminated=True,
                truncated=False,
                info=self._info_metrics(),
            )
        if dead:
            return StepResult(
                observation=self._obs(),
                reward=reward,
                terminated=True,
                truncated=False,
                info=self._info_metrics(),
            )
        if at_limit:
            return StepResult(
                observation=self._obs(),
                reward=reward,
                terminated=False,
                truncated=True,
                info=self._info_metrics(),
            )
        return StepResult(
            observation=self._obs(),
            reward=reward,
            terminated=False,
            truncated=False,
            info=self._info_metrics(),
        )

    def render(self, mode: str = "text") -> str:
        parts = []
        for row in self._grid:
            parts.append("".join(f"{v:5d}" if v else "    ." for v in row))
        parts.append(f"score={self._score} step={self._step_index} max={_max_tile(self._grid)}")
        return "\n".join(parts)
