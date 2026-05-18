#!/usr/bin/env python3
"""
run_local_episode.py — quick local smoke test / how-to-use example.

Spins up a tiny in-process mock environment, registers a Domain,
and runs one episode against it without needing a real model key.

Usage:
    uv run scripts/run_local_episode.py

Set ORCH_LITELLM_MODEL (default: "openai/gpt-4o-mini") and the
appropriate API key env var if you want a real model.
Use model="ollama/mistral" for a fully local run via Ollama.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# ── Tiny mock environment server ──────────────────────────────────────────────

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
]

_state: dict[str, dict] = {}


class MockEnvHandler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silence default logging
        pass

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length))

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json({"status": "ok"})

    def do_POST(self) -> None:
        body = self._read_json()
        ep = body.get("episode_id", "ep")

        if self.path == "/reset":
            seed = body.get("seed", 0)
            idx = seed % len(QUESTIONS)
            _state[ep] = {"idx": idx, "done": False}
            q = QUESTIONS[idx]
            self._send_json(
                {
                    "data": q,
                    "content_type": "application/json",
                }
            )

        elif self.path == "/step":
            action = body.get("action", "")
            st = _state.get(ep, {"idx": 0, "done": False})
            q = QUESTIONS[st["idx"]]
            correct = str(action).strip().upper() == q["answer"]
            _state[ep]["done"] = True
            self._send_json(
                {
                    "observation": {"data": {"result": "done"}, "content_type": "application/json"},
                    "reward": 1.0 if correct else 0.0,
                    "terminated": True,
                    "truncated": False,
                    "info": {"correct": str(correct), "answer": q["answer"]},
                }
            )

        elif self.path == "/close":
            _state.pop(ep, None)
            self._send_json({})


def _start_mock_server(port: int = 18765) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), MockEnvHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ── Main ──────────────────────────────────────────────────────────────────────


async def main() -> None:
    # Ensure data dir exists
    os.makedirs("./data", exist_ok=True)

    # Lazy imports so we can run from repo root without installing
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    from bench_common.core.binding_vow import (
        BindingVow,
        EpisodeSemantics,
        RewardSpec,
        SpaceSpec,
        SpaceType,
    )
    from bench_common.core.domain import Domain, EnvironmentEndpoint
    from bench_common.core.run import AgentConfig
    from bench_common.core.scoring import MetricDef, ScoringConfig
    from bench_common.orchestrator.service import run_test_episode
    from bench_common.storage.database import get_domain, init_db, save_domain

    await init_db()

    # Start mock env on localhost
    PORT = 18765
    server = _start_mock_server(PORT)
    print(f"[mock-env] listening on http://127.0.0.1:{PORT}")

    # Register domain (idempotent)
    domain_id = "local-trivia"
    if await get_domain(domain_id) is None:
        vow = BindingVow(
            id="local-trivia-v1",
            version="1.0.0",
            domain_id=domain_id,
            tier="tier1",
            observation_space=SpaceSpec(
                type=SpaceType.JSON,
                description="Multiple choice question dict",
            ),
            action_space=SpaceSpec(
                type=SpaceType.DISCRETE,
                enum_values=["A", "B", "C", "D"],
                description="Answer letter",
            ),
            reward=RewardSpec(
                type="binary",
                range={"low": 0.0, "high": 1.0},
                description="1 if correct",
            ),
            episode=EpisodeSemantics(max_steps=1, supports_seed=True),
            description="Local trivia quiz — mock environment",
        )
        domain = Domain(
            id=domain_id,
            name="Local Trivia",
            owner_id="local",
            binding_vow=vow,
            endpoint=EnvironmentEndpoint(
                mode="remote",
                url=f"http://127.0.0.1:{PORT}",
            ),
            scoring=ScoringConfig(
                primary_metric="success_rate",
                metrics=[
                    MetricDef(
                        name="success_rate",
                        type="terminal_field",
                        field="correct",
                        aggregation="pass_rate",
                    ),
                    MetricDef(
                        name="avg_reward",
                        type="episode_reward",
                        aggregation="mean",
                    ),
                ],
            ),
        )
        await save_domain(domain)
        print(f"[db] domain '{domain_id}' registered")
    else:
        print(f"[db] domain '{domain_id}' already exists")

    model = os.environ.get("ORCH_LITELLM_MODEL", "openai/gpt-4o-mini")
    print(f"[agent] using model: {model}")

    agent_config = AgentConfig(
        model=model,
        system_prompt=(
            "You are answering multiple choice questions. "
            "Reply with only the single letter of your answer (A, B, C, or D)."
        ),
        temperature=0.0,
    )

    print("\n[run] starting test episode (seed=0)…")
    episode = await run_test_episode(
        domain_id=domain_id,
        binding_vow_version="1.0.0",
        agent_config=agent_config,
        seed=0,
    )

    print(f"\n── Episode result ──────────────────────────")
    print(f"  id:           {episode.id}")
    print(f"  status:       {episode.status}")
    print(f"  steps:        {episode.steps}")
    print(f"  total_reward: {episode.total_reward}")
    print(f"  terminal_info:{episode.terminal_info}")
    print(f"────────────────────────────────────────────")

    server.shutdown()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
