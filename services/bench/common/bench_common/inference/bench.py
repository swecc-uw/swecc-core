"""
Model benchmarking runner.

Runs a model against a registered domain directly — no API server required.
Designed for fast local iteration, with Ollama as the primary target.

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
    uv run python -m src.inference.bench \\
        --model ollama/llama3.2 \\
        --domain simple-trivia \\
        --env-url http://localhost:8765 \\
        --episodes 10

    # Override system prompt inline
    uv run python -m src.inference.bench \\
        --model ollama/mistral \\
        --domain simple-trivia \\
        --env-url http://localhost:8765 \\
        --system "Answer with only the letter A, B, C, or D."
"""

from __future__ import annotations

from threading import Semaphore

import requests


# Replace async HttpEnvClient with synchronous requests
class HttpEnvClient:
    def __init__(self, env_url, timeout=5.0):
        self.env_url = env_url
        self.timeout = timeout

    def health(self):
        response = requests.get(f"{self.env_url}/health", timeout=self.timeout)
        return response.ok


from bench_common.core.run import AgentConfig, Episode, TechniqueConfig
from bench_common.runtime.agent_loop import AgentLoop
from bench_common.storage import database as db
from bench_common.storage.trace_store import TraceStore
from bench_common.techniques import TECHNIQUE_REGISTRY
from bench_common.techniques.base import Technique

log = structlog.get_logger()


def _build_techniques(domain_vow: Any) -> list[Technique]:
    techniques: list[Technique] = []
    for declaration in domain_vow.techniques:
        technique_cls = TECHNIQUE_REGISTRY.get(declaration.technique_id)
        if technique_cls is not None:
            techniques.append(technique_cls())
    return techniques


def _build_agent_techniques(domain_vow: Any) -> list[TechniqueConfig]:
    return [
        TechniqueConfig(technique_id=declaration.technique_id, params={})
        for declaration in domain_vow.techniques
        if declaration.technique_id in TECHNIQUE_REGISTRY
    ]


@dataclass
class BenchResult:
    model: str
    domain_id: str
    num_episodes: int
    episodes: list[Episode]
    elapsed_seconds: float
    scores: dict[str, float] = field(default_factory=dict)

    # ── derived stats ──────────────────────────────────────────────────────────

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
        # Box inner width = 38 chars.  Label prefix = 14 chars → value field = 24.
        W = 24

        def row(label: str, value: str) -> str:
            # label is already 14 chars (padded by caller); value truncated to W
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
                # label "    {name:<12} " = 4+12+1 = 17 chars, value field = 21
                n_str = name[:12]
                lines.append(f"║    {n_str:<12} {val:<21.4f}║")
        if self.failed:
            lines.append("╠══════════════════════════════════════╣")
            lines.append(row("  failed:     ", str(self.failed)))
        lines.append("╚══════════════════════════════════════╝")
        return "\n".join(lines)


def bench(model, domain_id, env_url, num_episodes):
    """
    Run *model* against *domain_id* for *num_episodes* episodes.

    Args:
        model:          LiteLLM model string — e.g. "ollama/llama3.2",
                        "ollama/mistral", "openai/gpt-4o-mini".
        domain_id:      ID of a registered Domain (must be in the local DB).
        env_url:        Base URL of the environment's HTTP server.
        num_episodes:   How many episodes to run (default 5).
        seed_set:       Explicit seeds — overrides num_episodes if provided.
        system_prompt:  Override the system prompt (otherwise uses Domain description).
        temperature:    Model temperature (default 0.0 for reproducibility).
        max_tokens:     Max tokens per model call (default 512).
        max_parallel:   Episode concurrency (default 1 — sequential).
        quiet:          Suppress per-episode progress output.

    Returns:
        BenchResult with episode list + computed scores.
    """
    db.init_db()

    domain = db.get_domain(domain_id)
    if domain is None:
        raise ValueError(
            f"Domain '{domain_id}' not found.\n"
            f"Register it first:\n"
            f"  uv run python docs/examples/simple_trivia/register.py\n"
            f"  # or POST /v1/domains"
        )

    # ── pre-flight: check env server is reachable ─────────────────────────────
    probe = HttpEnvClient(env_url)
    reachable = probe.health()
    if not reachable:
        raise ConnectionError(
            f"Environment server not reachable at {env_url}\n\n"
            f"Start it first, e.g.:\n"
            f"  uv run python docs/examples/simple_trivia/adapter.py\n"
            f"\nThen re-run this command."
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

    # Ephemeral trace store (writes to ./data/traces/ but not persisted to a Run)
    trace = TraceStore()
    inference = InferenceRouter()

    sem = Semaphore(max(1, max_parallel))
    start = time.monotonic()

    def _run_one(seed: int, idx: int) -> Episode:
        episode = Episode(
            run_id="bench",
            seed=seed,
            status="running",
            started_at=datetime.utcnow(),
        )
        async with sem:
            if not quiet:
                print(f"  [{idx+1}/{n}] seed={seed} …", end=" ", flush=True)
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

    if not quiet:
        print(f"\nBenching  model={model}  domain={domain_id}  episodes={n}")
        print(f"env →  {env_url}\n")

    tasks = [_run_one(seed, i) for i, seed in enumerate(seeds)]
    episodes = list(await asyncio.gather(*tasks))

    elapsed = time.monotonic() - start

    # Compute domain scores over completed episodes
    from bench_common.eval.metrics import compute_scores

    completed_eps = [e for e in episodes if e.status == "completed"]
    scores = compute_scores(domain.scoring, completed_eps) if completed_eps else {}

    return BenchResult(
        model=model,
        domain_id=domain_id,
        num_episodes=n,
        episodes=episodes,
        elapsed_seconds=elapsed,
        scores=scores,
    )


# ── CLI ────────────────────────────────────────────────────────────────────────


def _parse_args():
    import argparse

    p = argparse.ArgumentParser(
        prog="python -m src.inference.bench",
        description="Bench a model against a BenchAnything domain via Ollama (or any LiteLLM model).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Ollama (local)
  uv run python -m src.inference.bench --model ollama/llama3.2 --domain simple-trivia --env-url http://localhost:8765

  # Any LiteLLM model
  uv run python -m src.inference.bench --model openai/gpt-4o-mini --domain simple-trivia --env-url http://localhost:8765

  # More episodes, custom prompt
  uv run python -m src.inference.bench --model ollama/mistral --domain simple-trivia \\
      --env-url http://localhost:8765 --episodes 20 \\
      --system "Reply with only the letter A, B, C, or D."
        """,
    )
    p.add_argument(
        "--model",
        required=True,
        help='LiteLLM model string, e.g. "ollama/llama3.2", "ollama/mistral"',
    )
    p.add_argument(
        "--domain",
        required=True,
        dest="domain_id",
        help="Domain ID (must be registered in the local DB)",
    )
    p.add_argument(
        "--env-url",
        required=True,
        help="Base URL of the environment HTTP server, e.g. http://localhost:8765",
    )
    p.add_argument(
        "--episodes",
        type=int,
        default=5,
        dest="num_episodes",
        help="Number of episodes to run (default: 5)",
    )
    p.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=None,
        help="Explicit seed list (overrides --episodes)",
    )
    p.add_argument(
        "--system", default=None, dest="system_prompt", help="Override the system prompt"
    )
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument(
        "--parallel",
        type=int,
        default=1,
        dest="max_parallel",
        help="Episode concurrency (default: 1)",
    )
    return p.parse_args()


async def _main() -> None:
    args = _parse_args()
    result = await bench(
        model=args.model,
        domain_id=args.domain_id,
        env_url=args.env_url,
        num_episodes=args.num_episodes,
        seed_set=args.seeds,
        system_prompt=args.system_prompt,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        max_parallel=args.max_parallel,
    )
    print(result)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_main())
