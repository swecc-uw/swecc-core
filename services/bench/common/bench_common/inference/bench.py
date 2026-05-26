"""
Model benchmarking runner — no API server required.

Runs a model against a registered domain directly.  Designed for fast local
iteration and for the EC2 worker, with any LiteLLM-compatible model as the
target.

Programmatic usage:
    from bench_common.inference.bench import bench

    result = await bench(
        model="ollama/llama3.2",
        domain_id="simple-trivia",
        env_url="http://localhost:8765",
        num_episodes=10,
    )
    print(result)

CLI usage:
    python -m bench_common.inference.bench \\
        --model ollama/llama3.2 \\
        --domain simple-trivia \\
        --env-url http://localhost:8765 \\
        --episodes 10
"""

from __future__ import annotations

import asyncio
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from bench_common.core.run import AgentConfig, Episode, TechniqueConfig
from bench_common.env_sdk.registration import DomainConfig
from bench_common.eval.metrics import compute_scores
from bench_common.runtime.agent_loop import AgentLoop
from bench_common.runtime.env_client import HttpEnvClient
from bench_common.runtime.inference import InferenceRouter
from bench_common.storage import database as db
from bench_common.storage.trace_store import TraceStore
from bench_common.techniques import TECHNIQUE_REGISTRY
from bench_common.techniques.base import Technique

log = structlog.get_logger()


def _build_techniques(domain_vow: Any) -> list[Technique]:
    return [
        TECHNIQUE_REGISTRY[d.technique_id]()
        for d in domain_vow.techniques
        if d.technique_id in TECHNIQUE_REGISTRY
    ]


def _build_agent_techniques(domain_vow: Any) -> list[TechniqueConfig]:
    return [
        TechniqueConfig(technique_id=d.technique_id, params={})
        for d in domain_vow.techniques
        if d.technique_id in TECHNIQUE_REGISTRY
    ]


@dataclass
class BenchResult:
    model: str
    domain_id: str
    num_episodes: int
    episodes: list[Episode]
    elapsed_seconds: float
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def completed(self) -> int:
        return sum(1 for e in self.episodes if e.status == "completed")

    @property
    def failed(self) -> int:
        return sum(1 for e in self.episodes if e.status == "failed")

    @property
    def avg_reward(self) -> float:
        rewards = [e.total_reward for e in self.episodes if e.status == "completed"]
        return statistics.mean(rewards) if rewards else 0.0

    @property
    def avg_steps(self) -> float:
        steps = [e.steps for e in self.episodes if e.status == "completed"]
        return statistics.mean(steps) if steps else 0.0

    def __str__(self) -> str:
        W = 24

        def row(label: str, value: str) -> str:
            v = value[:W] if len(value) > W else value
            return f"║{label}{v:<{W}}║"

        ep_str = f"{self.completed}/{self.num_episodes} completed"
        lines = [
            "",
            "╔══════════════════════════════════════╗",
            "║         BenchAnything Results        ║",
            "╠══════════════════════════════════════╣",
            row("  model:      ", self.model),
            row("  domain:     ", self.domain_id),
            row("  episodes:   ", ep_str),
            row("  avg reward: ", f"{self.avg_reward:.4f}"),
            row("  avg steps:  ", f"{self.avg_steps:.2f}"),
            row("  wall time:  ", f"{self.elapsed_seconds:.1f}s"),
        ]
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


async def bench(
    model: str,
    domain_id: str,
    env_url: str,
    num_episodes: int = 5,
    seed_set: list[int] | None = None,
    system_prompt: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 512,
    max_parallel: int = 1,
    quiet: bool = False,
    *,
    domain: DomainConfig | None = None,
    allow_any_model: bool = False,
) -> BenchResult:
    """
    Run *model* against a domain for *num_episodes* episodes.

    Args:
        model:         LiteLLM model string, e.g. "ollama/llama3.2".
        domain_id:     Domain ID (for results labeling; also used for DB lookup).
        env_url:       Base URL of the environment's HTTP server.
        num_episodes:  How many episodes to run (default 5).
        seed_set:      Explicit seeds — overrides num_episodes if given.
        system_prompt: Override the system prompt; uses Domain description if None.
        temperature:   Model temperature (default 0.0 for reproducibility).
        max_tokens:    Max tokens per model call (default 512).
        max_parallel:  Episode concurrency (default 1 — sequential).
        quiet:         Suppress per-episode progress output.
        domain:        When set, use this config instead of loading from the platform DB
                       (for local ``mesocosm run local`` / benchanything.json workflows).
        allow_any_model: Skip the platform model allowlist (local dev with Ollama, etc.).

    Returns:
        BenchResult with episode list and computed domain scores.

    Raises:
        ValueError:       Domain not found or model not supported.
        ConnectionError:  Environment server not reachable at env_url.
    """
    if domain is None:
        await db.init_db()
        domain = await db.get_domain(domain_id)
        if domain is None:
            raise ValueError(
                f"Domain '{domain_id}' not found.\n"
                f"Register it first with POST /v1/domains, submit via mesocosm env submit, "
                f"or run locally with mesocosm run local (reads benchanything.json)."
            )
    elif domain_id != domain.id:
        domain_id = domain.id

    async with HttpEnvClient(env_url, timeout=5.0) as probe:
        if not await probe.health():
            raise ConnectionError(
                f"Environment server not reachable at {env_url}\n"
                f"Start the adapter first, then re-run."
            )

    seeds = seed_set if seed_set is not None else list(range(num_episodes))
    n = len(seeds)

    agent_config = AgentConfig(
        model=model,
        system_prompt=system_prompt,
        techniques=_build_agent_techniques(domain.binding_vow),
        temperature=temperature,
        max_tokens=max_tokens,
    )

    trace = TraceStore()
    inference = InferenceRouter(allow_any_model=allow_any_model)
    sem = asyncio.Semaphore(max(1, max_parallel))

    if not quiet:
        print(f"\nBenching  model={model}  domain={domain_id}  episodes={n}")
        print(f"env →  {env_url}\n")

    start = time.monotonic()

    async def _run_one(seed: int, idx: int) -> Episode:
        episode = Episode(
            run_id="bench",
            seed=seed,
            status="running",
            started_at=datetime.utcnow(),
        )
        async with sem:
            if not quiet:
                print(f"  [{idx + 1}/{n}] seed={seed} …", end=" ", flush=True)
            try:
                loop = AgentLoop(
                    binding_vow=domain.binding_vow,
                    agent_config=agent_config,
                    techniques=_build_techniques(domain.binding_vow),
                    inference=inference,
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
    completed_eps = [e for e in episodes if e.status == "completed"]
    scores = compute_scores(domain.scoring, completed_eps) if completed_eps else {}

    return BenchResult(
        model=model,
        domain_id=domain_id,
        num_episodes=n,
        episodes=list(episodes),
        elapsed_seconds=elapsed,
        scores=scores,
    )


# ── CLI ────────────────────────────────────────────────────────────────────────


def _parse_args():
    import argparse

    p = argparse.ArgumentParser(
        prog="python -m bench_common.inference.bench",
        description="Bench a model against a BenchAnything domain.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Ollama (local)
  python -m bench_common.inference.bench \\
      --model ollama/llama3.2 --domain simple-trivia --env-url http://localhost:8765

  # OpenAI (requires OPENAI_API_KEY)
  python -m bench_common.inference.bench \\
      --model openai/gpt-4o --domain simple-trivia --env-url http://localhost:8765

  # More episodes, custom system prompt
  python -m bench_common.inference.bench \\
      --model ollama/mistral --domain simple-trivia \\
      --env-url http://localhost:8765 --episodes 20 \\
      --system "Reply with only the letter A, B, C, or D."
""",
    )
    p.add_argument("--model", required=True, help="LiteLLM model string")
    p.add_argument("--domain", required=True, dest="domain_id", help="Domain ID")
    p.add_argument("--env-url", required=True, help="Environment HTTP server base URL")
    p.add_argument("--episodes", type=int, default=5, dest="num_episodes")
    p.add_argument("--seeds", type=int, nargs="+", default=None, dest="seed_set")
    p.add_argument("--system", default=None, dest="system_prompt")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--parallel", type=int, default=1, dest="max_parallel")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


async def _main() -> None:
    args = _parse_args()
    result = await bench(
        model=args.model,
        domain_id=args.domain_id,
        env_url=args.env_url,
        num_episodes=args.num_episodes,
        seed_set=args.seed_set,
        system_prompt=args.system_prompt,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        max_parallel=args.max_parallel,
        quiet=args.quiet,
    )
    print(result)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
