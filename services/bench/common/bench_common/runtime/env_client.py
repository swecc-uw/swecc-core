"""
HTTP environment client — the platform's side of the Gym-like interface.

Expected server contract (Section 5.2 of design doc):
  POST /reset   { "episode_id": "...", "seed": 42 }          → Observation JSON
  POST /step    { "episode_id": "...", "action": {...} }      → StepResult JSON
  POST /close   { "episode_id": "..." }                      → {}
  GET  /health                                               → { "status": "ok" }
"""
from __future__ import annotations

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
        return Observation(
            data=body.get("data", body),
            content_type=body.get("content_type", "application/json"),
            system_prompt=body.get("system_prompt"),
        )

    async def step(self, episode_id: str, action: Any) -> StepResult:
        r = await self._client.post(
            "/step", json={"episode_id": episode_id, "action": action}
        )
        r.raise_for_status()
        body = r.json()
        obs_raw = body.get("observation", {})
        return StepResult(
            observation=Observation(
                data=obs_raw.get("data", obs_raw),
                content_type=obs_raw.get("content_type", "application/json"),
            ),
            reward=float(body.get("reward", 0.0)),
            terminated=bool(body.get("terminated", False)),
            truncated=bool(body.get("truncated", False)),
            info={str(k): str(v) for k, v in body.get("info", {}).items()},
            system_prompt=body.get("system_prompt"),
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
