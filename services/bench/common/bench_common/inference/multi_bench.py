"""
Multi-agent benchmarking runner.

Analogous to bench_common.inference.bench but supports multiple named agents
competing in the same environment.  Each agent gets its own isolated inference
context and sliding-window episode memory.

Programmatic usage:
    from bench_common.inference.multi_bench import multi_bench
    from bench_common.core.run import AgentConfig

    result = await multi_bench(
        agents={
            "white": AgentConfig(model="anthropic/claude-sonnet-4-6"),
            "black": AgentConfig(model="openai/gpt-4o"),
        },
        domain_id="chess-v1",
        env_url="http://localhost:8765",
        num_episodes=5,
    )
    print(result)

Environment contract:
    The env adapter signals whose turn it is by including ``active_role`` in
    the ``info`` dict returned from /step, or in ``obs.data`` returned from
    /reset.  When neither is present the loop falls back to round-robin over
    the sorted agent keys (or the explicit ``role_order`` argument).

    Example /step response for a two-player game:
        {
          "observation": {"data": {"board": [...], "active_role": "black"}},
          "reward": 0.0,
          "terminated": false,
          "truncated": false,
          "info": {"active_role": "black"}
        }
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from bench_common.core.run import AgentConfig, Episode
from bench_common.env_sdk.registration import DomainConfig
from bench_common.eval.metrics import compute_scores
from bench_common.runtime.env_client import HttpEnvClient
from bench_common.runtime.inference import InferenceRouter
from bench_common.runtime.multi_agent_loop import MultiAgentLoop, RoleState
from bench_common.storage.trace_store import TraceStore
from bench_common.techniques.memory import EpisodicMemoryTechnique

log = structlog.get_logger()


@dataclass
class MultiBenchResult:
    """Aggregated result of a multi-agent bench run."""

    roles: dict[str, str]  # role → model string
    domain_id: str
    num_episodes: int
    episodes: list[Episode]
    elapsed_seconds: float
    scores: dict[str, float] = field(default_factory=dict)

    _SCOREABLE = frozenset({"completed", "truncated", "timeout"})

    @property
    def completed(self) -> int:
        return sum(1 for e in self.episodes if e.status == "completed")

    @property
    def truncated(self) -> int:
        return sum(1 for e in self.episodes if e.status in ("truncated", "timeout"))

    @property
    def failed(self) -> int:
        return sum(1 for e in self.episodes if e.status in ("failed", "cancelled"))

    @property
    def avg_reward(self) -> float:
        rewards = [e.total_reward for e in self.episodes if e.status in self._SCOREABLE]
        return sum(rewards) / len(rewards) if rewards else 0.0

    @property
    def avg_steps(self) -> float:
        steps = [e.steps for e in self.episodes if e.status in self._SCOREABLE]
        return sum(steps) / len(steps) if steps else 0.0

    def __str__(self) -> str:
        W = 24

        def row(label: str, value: str) -> str:
            v = value[:W] if len(value) > W else value
            return f"║{label}{v:<{W}}║"

        scoreable = self.completed + self.truncated
        ep_str = f"{scoreable}/{self.num_episodes} scoreable"
        lines = [
            "",
            "╔══════════════════════════════════════╗",
            "║     BenchAnything Multi-Agent        ║",
            "╠══════════════════════════════════════╣",
            row("  domain:     ", self.domain_id),
            row("  episodes:   ", ep_str),
            row("  avg reward: ", f"{self.avg_reward:.4f}"),
            row("  avg steps:  ", f"{self.avg_steps:.2f}"),
            row("  wall time:  ", f"{self.elapsed_seconds:.1f}s"),
            "╠══════════════════════════════════════╣",
            "║  agents:                             ║",
        ]
        for role, model in self.roles.items():
            lines.append(f"║    {role:<10} {model[:20]:<20}║")
        if self.scores:
            lines.append("╠══════════════════════════════════════╣")
            lines.append("║  domain scores:                      ║")
            for name, val in self.scores.items():
                n_str = name[:12]
                lines.append(f"║    {n_str:<12} {val:<21.4f}║")
        if self.failed:
            lines.append("╠══════════════════════════════════════╣")
            lines.append(row("  failed:     ", str(self.failed)))
        lines.append("╚══════════════════════════════════════╝")
        return "\n".join(lines)


async def multi_bench(
    agents: dict[str, AgentConfig],
    domain_id: str,
    env_url: str,
    num_episodes: int = 5,
    role_order: list[str] | None = None,
    window_size: int = 10,
    seed_set: list[int] | None = None,
    max_parallel: int = 1,
    quiet: bool = False,
    *,
    domain: DomainConfig | None = None,
    allow_any_model: bool = False,
) -> MultiBenchResult:
    """
    Run multiple named agents against a shared environment for *num_episodes* episodes.

    Args:
        agents:        Mapping of role name → AgentConfig.  Each role gets its own
                       InferenceRouter and EpisodicMemoryTechnique — fully isolated
                       context — while sharing the same env instance.
        domain_id:     Domain ID (for labeling; also used for DB lookup).
        env_url:       Base URL of the environment's HTTP server.
        num_episodes:  How many episodes to run (default 5).
        role_order:    Turn order for round-robin fallback when the env doesn't
                       signal ``active_role``.  Defaults to sorted(agents.keys()).
        window_size:   Sliding history window applied to every agent (default 10).
        seed_set:      Explicit seeds — overrides num_episodes if given.
        max_parallel:  Episode concurrency (default 1 — sequential).
        quiet:         Suppress per-episode progress output.
        domain:        Use this config directly instead of loading from the platform
                       DB (for local mesocosm / benchanything.json workflows).
        allow_any_model: Skip the platform model allowlist (local dev / Ollama).

    Returns:
        MultiBenchResult with episode list and computed domain scores.
    """
    if not agents:
        raise ValueError("agents must be non-empty")

    if domain is None:
        from bench_common.storage import database as db

        await db.init_db()
        domain = await db.get_domain(domain_id)
        if domain is None:
            raise ValueError(
                f"Domain '{domain_id}' not found.\n"
                f"Register it first or run locally with mesocosm run local."
            )
    elif domain_id != domain.id:
        domain_id = domain.id

    async with HttpEnvClient(env_url, timeout=5.0) as probe:
        if not await probe.health():
            raise ConnectionError(
                f"Environment server not reachable at {env_url}\n"
                f"Start the adapter first, then re-run."
            )

    resolved_order = role_order if role_order is not None else sorted(agents.keys())
    unknown = set(resolved_order) - set(agents.keys())
    if unknown:
        raise ValueError(f"role_order contains roles not in agents: {unknown}")

    seeds = seed_set if seed_set is not None else list(range(num_episodes))
    n = len(seeds)
    trace = TraceStore()
    sem = asyncio.Semaphore(max(1, max_parallel))

    if not quiet:
        roles_str = ", ".join(f"{r}={cfg.model}" for r, cfg in agents.items())
        print(f"\nMulti-agent bench  domain={domain_id}  episodes={n}")
        print(f"roles  → {roles_str}")
        print(f"order  → {resolved_order}")
        print(f"env    → {env_url}\n")

    start = time.monotonic()

    async def _run_one(seed: int, idx: int) -> Episode:
        episode = Episode(
            run_id="multi_bench",
            seed=seed,
            status="running",
            started_at=datetime.utcnow(),
        )
        async with sem:
            if not quiet:
                print(f"  [{idx + 1}/{n}] seed={seed} …", end=" ", flush=True)
            try:
                roles: dict[str, RoleState] = {
                    role: RoleState(
                        config=cfg,
                        inference=InferenceRouter(allow_any_model=allow_any_model),
                        memory=EpisodicMemoryTechnique(),
                        window_size=window_size,
                    )
                    for role, cfg in agents.items()
                }
                loop = MultiAgentLoop(
                    binding_vow=domain.binding_vow,
                    roles=roles,
                    role_order=resolved_order,
                    trace=trace,
                )
                async with HttpEnvClient(env_url) as env_client:
                    result = await loop.run_episode(
                        env_client=env_client,
                        episode_id=episode.id,
                        seed=seed,
                    )
                episode.status = result.status
                episode.steps = result.steps
                episode.total_reward = result.total_reward
                episode.terminal_info = result.terminal_info
                episode.ended_at = result.ended_at
                if not quiet:
                    print(f"reward={episode.total_reward:.2f}  steps={episode.steps}")
            except Exception as exc:
                episode.status = "failed"
                episode.terminal_info = {"error": str(exc)}
                episode.ended_at = datetime.utcnow()
                if not quiet:
                    print(f"FAILED: {exc}")
        return episode

    episodes: list[Episode] = await asyncio.gather(
        *[_run_one(seed, i) for i, seed in enumerate(seeds)]
    )

    elapsed = time.monotonic() - start
    _SCOREABLE = frozenset({"completed", "truncated", "timeout"})
    scoreable_eps = [e for e in episodes if e.status in _SCOREABLE]
    scores = compute_scores(domain.scoring, scoreable_eps) if scoreable_eps else {}

    return MultiBenchResult(
        roles={r: cfg.model for r, cfg in agents.items()},
        domain_id=domain_id,
        num_episodes=n,
        episodes=list(episodes),
        elapsed_seconds=elapsed,
        scores=scores,
    )
