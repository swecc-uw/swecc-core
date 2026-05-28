"""
HTTP environment client — the platform's side of the Gym-like interface.

Expected server contract (Section 5.2 of design doc):
  POST /reset   { "episode_id": "...", "seed": 42 }          → Observation JSON
  POST /step    { "episode_id": "...", "action": {...} }      → StepResult JSON
  POST /close   { "episode_id": "..." }                      → {}
  GET  /health                                               → { "status": "ok" }
"""

from __future__ import annotations

import math
from typing import Any

import httpx


class Observation:
    def __init__(
        self,
        data: Any,
        content_type: str = "application/json",
        system_prompt: str | None = None,
    ) -> None:
        self.data = data
        self.content_type = content_type
        self.system_prompt = system_prompt


class StepResult:
    def __init__(
        self,
        observation: Observation,
        reward: float,
        terminated: bool,
        truncated: bool,
        info: dict[str, Any],
        system_prompt: str | None = None,
    ) -> None:
        self.observation = observation
        self.reward = reward
        self.terminated = terminated
        self.truncated = truncated
        self.info = info
        self.system_prompt = system_prompt


class HttpEnvClient:
    """
    Connects to a remote environment over HTTP (Tier 1 fallback protocol).
    All methods are async and raise on non-2xx responses.
    """

    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base, timeout=timeout)

    async def health(self) -> bool:
        try:
            r = await self._client.get("/health")
            return r.status_code == 200
        except Exception:
            return False

    async def reset(self, episode_id: str, seed: int | None = None) -> Observation:
        payload: dict[str, Any] = {"episode_id": episode_id}
        if seed is not None:
            payload["seed"] = seed
        r = await self._client.post("/reset", json=payload)
        r.raise_for_status()
        body = r.json()
        return _parse_observation_body(body)

    async def step(self, episode_id: str, action: Any) -> StepResult:
        r = await self._client.post("/step", json={"episode_id": episode_id, "action": action})
        r.raise_for_status()
        body = r.json()
        if not isinstance(body, dict):
            raise ValueError(f"/step response must be a JSON object, got {type(body).__name__}")
        obs_raw = body.get("observation", {})
        return StepResult(
            observation=_parse_observation_body(obs_raw),
            reward=_parse_reward(body.get("reward", 0.0)),
            terminated=_parse_bool(body.get("terminated", False), "terminated"),
            truncated=_parse_bool(body.get("truncated", False), "truncated"),
            info=_parse_info(body.get("info", {})),
            system_prompt=_parse_optional_str(body.get("system_prompt"), "system_prompt"),
        )

    async def close(self, episode_id: str) -> None:
        r = await self._client.post("/close", json={"episode_id": episode_id})
        r.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "HttpEnvClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()


def _parse_optional_str(value: Any, field: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"{field} must be a string or null, got {type(value).__name__}")


def _parse_observation_body(body: Any) -> Observation:
    if isinstance(body, dict) and (
        "data" in body or "content_type" in body or "system_prompt" in body
    ):
        return Observation(
            data=body.get("data"),
            content_type=_parse_optional_str(
                body.get("content_type", "application/json"),
                "content_type",
            )
            or "application/json",
            system_prompt=_parse_optional_str(body.get("system_prompt"), "system_prompt"),
        )
    return Observation(data=body)


def _parse_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no", ""}:
            return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ValueError(f"{field} must be boolean-like, got {value!r}")


def _parse_reward(value: Any) -> float:
    try:
        reward = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"reward must be numeric, got {value!r}") from exc
    if not math.isfinite(reward):
        raise ValueError(f"reward must be finite, got {value!r}")
    return reward


def _parse_info(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"info must be a JSON object, got {type(value).__name__}")
    return {str(k): v for k, v in value.items()}
