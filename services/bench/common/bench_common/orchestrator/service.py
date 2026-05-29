"""
Orchestrator service — control plane for Runs and Episodes.

Uses asyncio background tasks instead of Celery+Redis.
Episode execution is capped by settings.max_parallel_episodes.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog
from bench_common.config import settings
from bench_common.mq_dispatch import publish_run_if_mq
from bench_common.core.run import AgentConfig, Episode, Run, RunConfig, TechniqueConfig
from bench_common.eval.metrics import _SCOREABLE_STATUSES, compute_scores
from bench_common.runtime.agent_loop import AgentLoop
from bench_common.runtime.env_client import HttpEnvClient
from bench_common.runtime.inference import InferenceRouter
from bench_common.storage import database as db
from bench_common.storage.trace_store import trace_store
from bench_common.techniques import TECHNIQUE_REGISTRY
from bench_common.techniques.base import Technique

log = structlog.get_logger()

_semaphore: asyncio.Semaphore | None = None
_active_run_tasks: dict[str, asyncio.Task] = {}
# Per-run set of in-flight episode tasks. cancel_run cancels them explicitly
# because asyncio.gather(..., return_exceptions=True) does NOT propagate
# cancellation to its children — without this, "cancelling" a run would just
# flip the DB status while episodes kept running and billing tokens.
_active_episode_tasks: dict[str, set[asyncio.Task]] = {}
_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.max_parallel_episodes)
    return _semaphore


def _build_techniques(agent_config: AgentConfig) -> list[Technique]:
    techniques: list[Technique] = []
    for tc in agent_config.techniques:
        cls = TECHNIQUE_REGISTRY.get(tc.technique_id)
        if cls:
            techniques.append(cls())
    return techniques


def _sandbox_env_id_from_url(env_url: str) -> str | None:
    """Extract env id from ``{sandbox}/envs/{id}`` proxy URLs."""
    path = urlparse(env_url).path.rstrip("/")
    parts = path.split("/")
    if len(parts) >= 2 and parts[-2] == "envs":
        return parts[-1]
    return None


async def _ensure_sandbox_env_running(env_url: str, github_url: str | None) -> None:
    """Re-clone dev env subprocesses after bench-sandbox restarts (in-memory state is lost)."""
    if not github_url:
        return
    env_id = _sandbox_env_id_from_url(env_url)
    if not env_id:
        return
    health_url = f"{settings.sandbox_url.rstrip('/')}/envs/{env_id}/health"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(health_url)
            if resp.status_code == 200:
                return
        except httpx.TransportError:
            pass
        clone_resp = await client.post(
            f"{settings.sandbox_url.rstrip('/')}/clone",
            json={"env_id": env_id, "github_url": github_url},
            timeout=120.0,
        )
        clone_resp.raise_for_status()
    log.info("sandbox_env_recloned", env_id=env_id)


async def _github_url_for_domain(domain_id: str) -> str | None:
    envs = await db.list_developer_environments(domain_id=domain_id)
    return envs[0].get("github_url") if envs else None


async def _resolve_episode_env_url(
    domain: Any,
    env_id: str | None,
) -> tuple[str | None, str | None]:
    github_url = await _github_url_for_domain(domain.id)
    env_url = domain.endpoint.url
    if not env_id:
        return env_url, github_url

    env = await db.get_developer_environment(env_id)
    if env:
        github_url = env.get("github_url") or github_url
        if domain.endpoint.mode == "sandbox" and domain.endpoint.url:
            env_url = domain.endpoint.url
        else:
            env_url = env.get("env_url") or domain.endpoint.url
    return env_url, github_url


async def create_run(config: RunConfig, requester_id: str) -> Run:
    # Validate domain + binding vow
    domain = await db.get_domain(config.domain_id)
    if domain is None:
        raise ValueError(f"Domain '{config.domain_id}' not found")

    vow = domain.binding_vow
    if vow.version != config.binding_vow_version:
        raise ValueError(
            f"Binding vow version mismatch: domain has {vow.version!r}, "
            f"requested {config.binding_vow_version!r}"
        )

    # Validate requested techniques against the vow
    declared_ids = {t.technique_id for t in vow.techniques}
    for tc in config.agent_config.techniques:
        if tc.technique_id not in declared_ids:
            raise ValueError(f"Technique '{tc.technique_id}' not declared in binding vow")

    run = Run(
        config=config,
        requester_id=requester_id,
        status="running",
        env_id=config.env_id,
    )
    await db.save_run(run, env_id=config.env_id)

    # Create episode records
    seeds = config.seed_set or list(range(config.num_episodes))
    episodes = [Episode(run_id=run.id, seed=seed, status="pending") for seed in seeds]
    for ep in episodes:
        await db.save_episode(ep)

    if settings.mq_enabled:
        await publish_run_if_mq(run.id)
    else:
        _schedule_run_execution(run, episodes, domain)

    log.info("run_created", run_id=run.id, num_episodes=len(episodes), mq=settings.mq_enabled)
    return run


def _schedule_run_execution(run: Run, episodes: list[Episode], domain: Any) -> None:
    task = asyncio.create_task(_run_all_episodes(run, episodes, domain))
    _active_run_tasks[run.id] = task
    task.add_done_callback(lambda _t, rid=run.id: _active_run_tasks.pop(rid, None))


async def execute_run(run_id: str) -> None:
    """MQ consumer entry: load run/episodes/domain and execute pending work."""
    run = await db.get_run(run_id)
    if run is None:
        log.warning("execute_run_missing", run_id=run_id)
        return
    if run.status in _TERMINAL_RUN_STATUSES:
        log.info("execute_run_skip_terminal", run_id=run_id, status=run.status)
        return

    episodes = await db.get_episodes(run_id)
    work_eps = [ep for ep in episodes if ep.status in ("pending", "running")]
    if not work_eps:
        log.info("execute_run_skip_no_work", run_id=run_id, run_status=run.status)
        return

    domain = await db.get_domain(run.config.domain_id)
    if domain is None:
        log.error("execute_run_domain_missing", run_id=run_id, domain_id=run.config.domain_id)
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        await db.save_run(run, env_id=run.env_id)
        return

    if run_id in _active_run_tasks and not _active_run_tasks[run_id].done():
        log.info("execute_run_skip_inflight", run_id=run_id)
        return

    log.info("execute_run_start", run_id=run_id, num_episodes=len(work_eps))
    task = asyncio.create_task(_run_all_episodes(run, work_eps, domain))
    _active_run_tasks[run_id] = task
    try:
        await task
    finally:
        _active_run_tasks.pop(run_id, None)


async def _run_is_cancelled(run_id: str) -> bool:
    run = await db.get_run(run_id)
    return run is not None and run.status == "cancelled"


async def cancel_run(run_id: str) -> Run:
    """Stop a run: cancel background work and mark pending/running episodes cancelled."""
    run = await db.get_run(run_id)
    if run is None:
        raise ValueError(f"Run '{run_id}' not found")
    if run.status in _TERMINAL_RUN_STATUSES:
        return run

    run.status = "cancelled"
    run.completed_at = datetime.utcnow()
    await db.save_run(run)

    # Cancel each in-flight episode task first, then the parent. Otherwise
    # gather()'s children survive parent cancellation and continue making
    # inference + env calls until they reach a natural terminal state, at
    # which point _run_episode would overwrite the cancelled episode row.
    ep_tasks = _active_episode_tasks.get(run_id, set())
    for ep_task in list(ep_tasks):
        if not ep_task.done():
            ep_task.cancel()

    bg = _active_run_tasks.pop(run_id, None)
    if bg is not None and not bg.done():
        bg.cancel()

    for ep in await db.get_episodes(run_id):
        if ep.status in ("pending", "running"):
            ep.status = "cancelled"
            ep.ended_at = datetime.utcnow()
            ep.terminal_info = {"cancelled": True, "reason": "run_cancelled"}
            await db.save_episode(ep)

    log.info("run_cancelled", run_id=run_id)
    return run


async def _run_all_episodes(run: Run, episodes: list[Episode], domain: Any) -> None:
    run_id = run.id
    ep_tasks: set[asyncio.Task] = set()
    _active_episode_tasks[run_id] = ep_tasks
    try:
        sem = _get_semaphore()
        for ep in episodes:
            t = asyncio.create_task(
                _run_episode(ep, run.config.agent_config, domain, sem, env_id=run.env_id)
            )
            ep_tasks.add(t)
            t.add_done_callback(ep_tasks.discard)
        try:
            await asyncio.gather(*ep_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            log.info("run_task_cancelled", run_id=run_id)
            for t in list(ep_tasks):
                if not t.done():
                    t.cancel()
            # Drain so episodes finish their cancellation cleanup before we proceed.
            await asyncio.gather(*ep_tasks, return_exceptions=True)
            run = await db.get_run(run_id)
            if run is not None and run.status == "running":
                run.status = "cancelled"
                run.completed_at = datetime.utcnow()
                await db.save_run(run)
            raise
    finally:
        _active_episode_tasks.pop(run_id, None)

    run = await db.get_run(run_id)
    if run is None or run.status == "cancelled":
        return

    all_eps = await db.get_episodes(run_id)
    if await _run_is_cancelled(run_id):
        return

    # Guard the leaderboard against partial-credit phantoms: a run where only
    # 1/10 episodes completed would otherwise post the lucky completion's
    # reward as if it were the full N-episode average.  Require a configurable
    # minimum scoreable fraction before publishing scores.
    if not all_eps:
        # Defence-in-depth: RunConfig.num_episodes >= 1 should prevent this,
        # but if episode creation failed silently we'd otherwise score [] = 0.0.
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        await db.save_run(run, env_id=run.env_id)
        log.warning("run_no_episodes_recorded", run_id=run_id)
        return

    scoreable_eps = [ep for ep in all_eps if ep.status in _SCOREABLE_STATUSES]
    scoreable_ratio = len(scoreable_eps) / len(all_eps)
    if scoreable_ratio < settings.min_scoreable_episode_ratio:
        run.status = "failed"
        run.completed_at = datetime.utcnow()
        await db.save_run(run, env_id=run.env_id)
        log.warning(
            "run_insufficient_scoreable_episodes",
            run_id=run_id,
            num_episodes=len(all_eps),
            scoreable=len(scoreable_eps),
            required_ratio=settings.min_scoreable_episode_ratio,
            statuses={ep.status for ep in all_eps},
        )
        return

    scores = compute_scores(domain.scoring, all_eps)
    run.scores = scores
    run.status = "completed"
    run.completed_at = datetime.utcnow()
    await db.save_run(run, env_id=run.env_id)

    log.info("run_completed", run_id=run_id, scores=scores)


async def _run_episode(
    episode: Episode,
    agent_config: AgentConfig,
    domain: Any,
    sem: asyncio.Semaphore,
    *,
    env_id: str | None = None,
) -> Episode:
    async with sem:
        episode.status = "running"
        episode.started_at = datetime.utcnow()
        await db.save_episode(episode)

        env_url, github_url = await _resolve_episode_env_url(domain, env_id)
        if not env_url:
            episode.status = "failed"
            episode.terminal_info = {"error": "No environment URL configured"}
            await db.save_episode(episode)
            return episode

        try:
            await _ensure_sandbox_env_running(env_url, github_url)
            techniques = _build_techniques(agent_config)
            inference = InferenceRouter()
            loop = AgentLoop(
                binding_vow=domain.binding_vow,
                agent_config=agent_config,
                techniques=techniques,
                inference=inference,
                trace=trace_store,
            )

            async with HttpEnvClient(env_url) as env_client:
                result = await loop.run_episode(
                    env_client=env_client,
                    episode_id=episode.id,
                    seed=episode.seed,
                )

            episode.status = result.status
            episode.steps = result.steps
            episode.total_reward = result.total_reward
            episode.terminal_info = result.terminal_info
            episode.ended_at = result.ended_at

        except asyncio.CancelledError:
            episode.status = "cancelled"
            episode.terminal_info = {"cancelled": True, "reason": "run_cancelled"}
            episode.ended_at = datetime.utcnow()
            await db.save_episode(episode)
            raise
        except Exception as exc:
            log.exception("episode_failed", episode_id=episode.id, error=str(exc))
            episode.status = "failed"
            episode.terminal_info = {"error": str(exc)}
            episode.ended_at = datetime.utcnow()

        await db.save_episode(episode)
        return episode


async def run_test_episode(
    domain_id: str,
    binding_vow_version: str,
    agent_config: AgentConfig,
    env_url: str | None = None,
    seed: int | None = None,
    github_url: str | None = None,
    env_id: str | None = None,
) -> Episode:
    """Run a single ephemeral episode (Development Mode)."""
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise ValueError(f"Domain '{domain_id}' not found")

    # Sandbox domains must hit the proxy (/envs/{id}), not a direct subprocess port.
    if domain.endpoint.mode == "sandbox" and domain.endpoint.url:
        effective_url = domain.endpoint.url
    else:
        effective_url = env_url or domain.endpoint.url
    if not effective_url:
        raise ValueError("No environment URL provided or configured on domain")

    repo_url = github_url or await _github_url_for_domain(domain_id)
    await _ensure_sandbox_env_running(effective_url, repo_url)

    run = Run(
        config=RunConfig(
            domain_id=domain_id,
            binding_vow_version=binding_vow_version,
            agent_config=agent_config,
            num_episodes=1,
            env_id=env_id,
        ),
        requester_id="test",
        status="running",
        env_id=env_id,
    )
    await db.save_run(run, env_id=env_id)

    episode = Episode(
        run_id=run.id,
        seed=seed,
        status="running",
        started_at=datetime.utcnow(),
    )
    await db.save_episode(episode)

    try:
        techniques = _build_techniques(agent_config)
        inference = InferenceRouter()
        loop = AgentLoop(
            binding_vow=domain.binding_vow,
            agent_config=agent_config,
            techniques=techniques,
            inference=inference,
            trace=trace_store,
        )

        async with HttpEnvClient(effective_url) as env_client:
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

    except asyncio.CancelledError:
        # Task was cancelled externally — persist terminal state before re-raising
        # so the episode and run don't stay stuck in "running" forever.
        episode.status = "cancelled"
        episode.terminal_info = {"cancelled": True, "reason": "task_cancelled"}
        episode.ended_at = datetime.utcnow()
        await db.save_episode(episode)
        run.status = "cancelled"
        run.completed_at = datetime.utcnow()
        await db.save_run(run, env_id=env_id)
        raise

    except Exception as exc:
        log.exception("test_episode_failed", episode_id=episode.id, error=str(exc))
        episode.status = "failed"
        episode.terminal_info = {"error": str(exc)}
        episode.ended_at = datetime.utcnow()

    await db.save_episode(episode)

    run.status = "completed" if episode.status == "completed" else "failed"
    run.completed_at = datetime.utcnow()
    run.scores = compute_scores(domain.scoring, [episode])
    await db.save_run(run, env_id=env_id)

    return episode
