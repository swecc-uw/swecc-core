"""
Agent loop — the inner execution engine for a single episode.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog

from bench_common.core.binding_vow import BindingVow
from bench_common.core.run import AgentConfig, Episode, TraceEvent
from bench_common.runtime.env_client import HttpEnvClient, Observation
from bench_common.runtime.inference import InferenceRouter
from bench_common.storage.trace_store import TraceStore

log = structlog.get_logger()


class AgentLoop:
    def __init__(
        self,
        binding_vow: BindingVow,
        agent_config: AgentConfig,
        techniques: list[Any],  # list[Technique]
        inference: InferenceRouter,
        trace: TraceStore,
    ) -> None:
        self.vow = binding_vow
        self.config = agent_config
        self.techniques = techniques
        self.inference = inference
        self.trace = trace
        self.state: dict[str, Any] = {}

    async def run_episode(
        self,
        env_client: HttpEnvClient,
        episode_id: str,
        seed: int | None,
    ) -> Episode:
        episode = Episode(
            id=episode_id,
            run_id="",  # caller fills in
            seed=seed,
            status="running",
            started_at=datetime.utcnow(),
        )

        await self.trace.append(
            TraceEvent(
                episode_id=episode_id,
                step=0,
                event_type="episode_start",
                payload={"seed": seed},
            )
        )

        # ── technique on_episode_start ────────────────────────────────────────
        for technique in self.techniques:
            await technique.on_episode_start(
                episode_id, self.config.techniques_for(technique.id())
            )

        obs = await env_client.reset(episode_id=episode_id, seed=seed)
        env_system_prompt: str | None = obs.system_prompt
        await self.trace.append(
            TraceEvent(
                episode_id=episode_id,
                step=0,
                event_type="observation",
                payload={
                    "data": obs.data,
                    "content_type": obs.content_type,
                    "system_prompt": obs.system_prompt,
                },
            )
        )

        step = 0
        total_reward = 0.0
        result = None
        max_steps = self.vow.episode.max_steps
        max_wall = self.vow.episode.max_wall_seconds
        deadline = (
            datetime.utcnow().timestamp() + max_wall if max_wall else None
        )

        while True:
            step += 1

            # wall-time timeout
            if deadline and datetime.utcnow().timestamp() > deadline:
                episode.status = "timeout"
                break

            # ── pre-action technique pass ─────────────────────────────────────
            augmented_context: dict[str, Any] = {}
            for technique in self.techniques:
                ctx = await technique.before_action(obs, self.state)
                augmented_context.update(ctx)

            # ── model inference ───────────────────────────────────────────────
            action = await self.inference.decide(
                observation=obs,
                binding_vow=self.vow,
                agent_config=self.config,
                extra_context=augmented_context,
                step=step,
                env_system_prompt=env_system_prompt,
            )
            await self.trace.append(
                TraceEvent(
                    episode_id=episode_id,
                    step=step,
                    event_type="action",
                    payload={"action": action},
                )
            )

            # ── environment step ──────────────────────────────────────────────
            result = await env_client.step(episode_id=episode_id, action=action)
            total_reward += result.reward
            await self.trace.append(
                TraceEvent(
                    episode_id=episode_id,
                    step=step,
                    event_type="step_result",
                    payload={
                        "reward": result.reward,
                        "terminated": result.terminated,
                        "truncated": result.truncated,
                        "info": result.info,
                        "system_prompt": result.system_prompt,
                    },
                )
            )

            # ── carry env system prompt forward ───────────────────────────────
            if result.system_prompt is not None:
                env_system_prompt = result.system_prompt

            # ── post-action technique pass ────────────────────────────────────
            for technique in self.techniques:
                await technique.after_action(action, result, self.state)

            if result.terminated or result.truncated:
                episode.status = "completed"
                break
            if max_steps and step >= max_steps:
                episode.status = "completed"
                break

            obs = result.observation

        terminal_info = result.info if result else {}

        # ── clean up env instance ─────────────────────────────────────────────
        try:
            await env_client.close(episode_id=episode_id)
        except Exception:
            log.warning("env_close_failed", episode_id=episode_id)

        # ── technique on_episode_end ──────────────────────────────────────────
        for technique in self.techniques:
            await technique.on_episode_end(episode_id, terminal_info)

        await self.trace.append(
            TraceEvent(
                episode_id=episode_id,
                step=step,
                event_type="episode_end",
                payload={
                    "total_reward": total_reward,
                    "steps": step,
                    "status": episode.status,
                    "terminal_info": terminal_info,
                },
            )
        )

        episode.steps = step
        episode.total_reward = total_reward
        episode.terminal_info = terminal_info
        episode.ended_at = datetime.utcnow()
        if episode.status == "running":
            episode.status = "completed"

        log.info(
            "episode_done",
            episode_id=episode_id,
            steps=step,
            total_reward=total_reward,
            status=episode.status,
        )
        return episode
