from __future__ import annotations

from typing import Any

import pytest
from bench_common.env_sdk.base import BaseEnv, StepResult
from bench_common.env_sdk.server import create_env_app
from fastapi.testclient import TestClient


class _CountingEnv(BaseEnv):
    def __init__(self) -> None:
        self.steps = 0

    def reset(self, seed: int | None = None, **params: Any) -> dict[str, str]:
        self.steps = 0
        return {"ok": "reset"}

    def step(self, action: Any) -> StepResult:
        self.steps += 1
        return StepResult(
            observation={"step": self.steps},
            reward=0.0,
            terminated=False,
            truncated=False,
            info={"step": str(self.steps)},
        )


def test_adapter_step_cap_truncates_without_calling_env() -> None:
    app = create_env_app(_CountingEnv, max_steps=2)
    client = TestClient(app)
    eid = "ep-1"

    client.post("/reset", json={"episode_id": eid})
    assert (
        client.post("/step", json={"episode_id": eid, "action": "a"}).json()["truncated"] is False
    )
    assert (
        client.post("/step", json={"episode_id": eid, "action": "b"}).json()["truncated"] is False
    )

    capped = client.post("/step", json={"episode_id": eid, "action": "c"}).json()
    assert capped["truncated"] is True
    assert capped["info"]["reason"] == "step_limit"
    assert capped["info"]["max_steps"] == "2"


def test_create_env_app_rejects_non_positive_max_steps() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        create_env_app(_CountingEnv, max_steps=0)
