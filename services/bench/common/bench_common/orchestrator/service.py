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

import structlog
from bench_common.config import settings
from bench_common.core.run import AgentConfig, Episode, Run, RunConfig, TechniqueConfig
from bench_common.eval.metrics import compute_scores
from bench_common.runtime.agent_loop import AgentLoop
from bench_common.runtime.env_client import HttpEnvClient
from bench_common.runtime.inference import InferenceRouter
from bench_common.storage import database as db
from bench_common.storage.trace_store import trace_store
from bench_common.techniques import TECHNIQUE_REGISTRY
from bench_common.techniques.base import Technique

log = structlog.get_logger()

_semaphore: asyncio.Semaphore | None = None


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
            raise ValueError(
                f"Technique '{tc.technique_id}' not declared in binding vow"
            )

    run = Run(config=config, requester_id=requester_id, status="running")
    await db.save_run(run)

    # Create episode records
    seeds = config.seed_set or list(range(config.num_episodes))
    episodes = [Episode(run_id=run.id, seed=seed, status="pending") for seed in seeds]
    for ep in episodes:
        await db.save_episode(ep)

    # Schedule episodes as background tasks
    asyncio.create_task(_run_all_episodes(run, episodes, domain))

    log.info("run_created", run_id=run.id, num_episodes=len(episodes))
    return run


async def _run_all_episodes(run: Run, episodes: list[Episode], domain: Any) -> None:
    sem = _get_semaphore()
    tasks = [
        asyncio.create_task(_run_episode(ep, run.config.agent_config, domain, sem))
        for ep in episodes
    ]
    completed_episodes = await asyncio.gather(*tasks, return_exceptions=True)

    # Reload run from DB (status may have changed)
    run = await db.get_run(run.id)
    if run is None:
        return

    all_eps = await db.get_episodes(run.id)

    # Compute scores
    scores = compute_scores(domain.scoring, all_eps)
    run.scores = scores
    run.status = "completed"
    run.completed_at = datetime.utcnow()
    await db.save_run(run)

    log.info("run_completed", run_id=run.id, scores=scores)


async def _run_episode(
    episode: Episode,
    agent_config: AgentConfig,
    domain: Any,
    sem: asyncio.Semaphore,
) -> Episode:
    async with sem:
        episode.status = "running"
        episode.started_at = datetime.utcnow()
        await db.save_episode(episode)

        env_url = domain.endpoint.url
        if not env_url:
            episode.status = "failed"
            episode.terminal_info = {"error": "No environment URL configured"}
            await db.save_episode(episode)
            return episode

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

    run = Run(
        config=RunConfig(
            domain_id=domain_id,
            binding_vow_version=binding_vow_version,
            agent_config=agent_config,
            num_episodes=1,
        ),
        requester_id="test",
        status="running",
    )
    await db.save_run(run)

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

    except Exception as exc:
        log.exception("test_episode_failed", episode_id=episode.id, error=str(exc))
        episode.status = "failed"
        episode.terminal_info = {"error": str(exc)}
        episode.ended_at = datetime.utcnow()

    await db.save_episode(episode)

    run.status = "completed" if episode.status == "completed" else "failed"
    run.completed_at = datetime.utcnow()
    run.scores = compute_scores(domain.scoring, [episode])
    await db.save_run(run)

    return episode
