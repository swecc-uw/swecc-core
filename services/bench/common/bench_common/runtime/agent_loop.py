"""
Agent loop — the inner execution engine for a single episode.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Coroutine, TypeVar

import structlog
from bench_common.config import settings
from bench_common.core.binding_vow import BindingVow
from bench_common.core.run import AgentConfig, Episode, TraceEvent
from bench_common.runtime.env_client import HttpEnvClient, Observation
from bench_common.runtime.inference import InferenceRouter, normalize_model_id
from bench_common.storage.trace_store import TraceStore

log = structlog.get_logger()

_T = TypeVar("_T")
_DEFAULT_PLATFORM_MAX_STEPS = 35


def _platform_max_steps() -> int:
    platform_cap = settings.max_episode_steps
    if platform_cap <= 0:
        return _DEFAULT_PLATFORM_MAX_STEPS
    return platform_cap


def _effective_max_steps(declared_max_steps: int | None) -> int:
    """Return the enforced episode step budget.

    The platform owns the safety ceiling. Binding Vows can make an env shorter
    for task semantics, but they cannot expand execution past the platform cap.
    """
    platform_cap = _platform_max_steps()
    if declared_max_steps is None:
        return platform_cap
    return min(declared_max_steps, platform_cap)


async def _with_deadline(coro: Coroutine[Any, Any, _T], deadline: float | None) -> _T:
    """Await *coro*, raising asyncio.TimeoutError if *deadline* (UTC timestamp) has passed.

    Unlike a polled deadline check at the top of the loop, this actually
    interrupts a slow inference call or env step mid-flight.
    """
    if deadline is None:
        return await coro
    remaining = deadline - datetime.utcnow().timestamp()
    if remaining <= 0:
        coro.close()  # prevent ResourceWarning on the unawaited coroutine
        raise asyncio.TimeoutError()
    return await asyncio.wait_for(coro, timeout=remaining)


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
            await technique.on_episode_start(episode_id, self.config.techniques_for(technique.id()))

        obs = await env_client.reset(episode_id=episode_id, seed=seed)
        env_system_prompt: str | None = obs.system_prompt
        await self.trace.append(
            TraceEvent(
                episode_id=episode_id,
                step=0,
                event_type="observation",
                payload={
                    "phase": "start",
                    "data": obs.data,
                    "content_type": obs.content_type,
                    "system_prompt": obs.system_prompt,
                },
            )
        )

        step = 0
        total_reward = 0.0
        result = None
        declared_max_steps = self.vow.episode.max_steps
        max_steps = _effective_max_steps(declared_max_steps)
        max_wall = self.vow.episode.max_wall_seconds
        deadline = datetime.utcnow().timestamp() + max_wall if max_wall else None
        terminal_info: dict[str, Any] | None = None
        # Cost circuit breaker — hard cap on cumulative inference tokens.
        # Without this, a buggy agent in a tool-call loop or one fed an
        # ever-growing observation will keep paying $$ until the wall-time
        # deadline fires (which may be minutes away or never set).
        total_tokens = 0
        token_budget = settings.max_tokens_per_episode

        try:
            # Wrap the entire episode loop so env_client.close() is always called
            # — on normal exit, on exceptions from inference/step, and on CancelledError.
            while True:
                step += 1

                # ── pre-action technique pass ─────────────────────────────────────
                augmented_context: dict[str, Any] = {}
                for technique in self.techniques:
                    ctx = await technique.before_action(obs, self.state)
                    augmented_context.update(ctx)

                await self.trace.append(
                    TraceEvent(
                        episode_id=episode_id,
                        step=step,
                        event_type="observation",
                        payload={
                            "phase": "before_agent",
                            "data": obs.data,
                            "content_type": obs.content_type,
                            "system_prompt": obs.system_prompt,
                        },
                    )
                )

                # ── model inference ───────────────────────────────────────────────
                # _with_deadline interrupts mid-call if the wall-time budget is
                # exhausted, rather than just checking between steps.
                try:
                    decision = await _with_deadline(
                        self.inference.decide(
                            observation=obs,
                            binding_vow=self.vow,
                            agent_config=self.config,
                            extra_context=augmented_context,
                            step=step,
                            env_system_prompt=env_system_prompt,
                        ),
                        deadline,
                    )
                except asyncio.TimeoutError:
                    episode.status = "timeout"
                    terminal_info = {"reason": "wall_time_limit"}
                    break

                # Token accounting: surface per-step usage on the trace so cost
                # is observable, then trip the breaker if the cumulative total
                # crosses the per-episode budget.
                total_tokens += decision.total_tokens
                if decision.total_tokens > 0:
                    await self.trace.append(
                        TraceEvent(
                            episode_id=episode_id,
                            step=step,
                            event_type="technique_event",
                            payload={
                                "kind": "token_usage",
                                "step_tokens": decision.total_tokens,
                                "prompt_tokens": decision.prompt_tokens,
                                "completion_tokens": decision.completion_tokens,
                                "cumulative_tokens": total_tokens,
                            },
                        )
                    )
                if token_budget > 0 and total_tokens > token_budget:
                    log.warning(
                        "episode_token_budget_exceeded",
                        episode_id=episode_id,
                        total_tokens=total_tokens,
                        budget=token_budget,
                        step=step,
                    )
                    episode.status = "failed"
                    terminal_info = {
                        "reason": "token_budget_exceeded",
                        "total_tokens": total_tokens,
                        "budget": token_budget,
                    }
                    break

                if decision.reasoning_text:
                    await self.trace.append(
                        TraceEvent(
                            episode_id=episode_id,
                            step=step,
                            event_type="model_call",
                            payload={
                                "text": decision.reasoning_text,
                                "model": normalize_model_id(self.config.model),
                            },
                        )
                    )
                await self.trace.append(
                    TraceEvent(
                        episode_id=episode_id,
                        step=step,
                        event_type="action",
                        payload={"action": decision.action},
                    )
                )

                # ── environment step ──────────────────────────────────────────────
                try:
                    result = await _with_deadline(
                        env_client.step(episode_id=episode_id, action=decision.action),
                        deadline,
                    )
                except asyncio.TimeoutError:
                    episode.status = "timeout"
                    terminal_info = {"reason": "wall_time_limit"}
                    break

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
                await self.trace.append(
                    TraceEvent(
                        episode_id=episode_id,
                        step=step,
                        event_type="observation",
                        payload={
                            "phase": "after_env",
                            "data": result.observation.data,
                            "content_type": result.observation.content_type,
                            "system_prompt": result.observation.system_prompt,
                        },
                    )
                )

                # ── carry env system prompt forward ───────────────────────────────
                if result.system_prompt is not None:
                    env_system_prompt = result.system_prompt

                # ── post-action technique pass ────────────────────────────────────
                for technique in self.techniques:
                    await technique.after_action(decision.action, result, self.state)

                if result.terminated or result.truncated:
                    episode.status = "completed"
                    break

                # Step budget exhausted — episode did not reach a natural terminal
                # state.  Use "truncated" (not "completed") so scoring and callers
                # can distinguish a budget cut-off from a genuine task completion.
                if step >= max_steps:
                    episode.status = "truncated"
                    terminal_info = {
                        **result.info,
                        "reason": result.info.get("reason", "step_limit"),
                        "max_steps": max_steps,
                        "declared_max_steps": declared_max_steps,
                        "platform_max_steps": _platform_max_steps(),
                    }
                    break

                obs = result.observation

        finally:
            # ── clean up env instance ─────────────────────────────────────────
            # Runs on normal exit, exception, and CancelledError — env adapter
            # server won't leak the episode's BaseEnv instance.
            try:
                await env_client.close(episode_id=episode_id)
            except Exception:
                log.warning("env_close_failed", episode_id=episode_id)

        if terminal_info is None:
            terminal_info = result.info if result else {}
        # Always surface the final cumulative token count so leaderboards and
        # cost dashboards can attribute spend without re-summing trace events.
        terminal_info = {**terminal_info, "total_tokens": total_tokens}

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
                    "total_tokens": total_tokens,
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
