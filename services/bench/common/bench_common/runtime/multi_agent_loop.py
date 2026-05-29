"""
Multi-agent episode loop.

Each named role gets its own AgentConfig, InferenceRouter, and
EpisodicMemoryTechnique, so agents have fully isolated context (their own
history/sliding-window) while sharing the same environment instance and board
state via the env's observation.

The environment signals whose turn it is via ``active_role`` in the step info
dict or in obs.data on reset.  Falls back to round-robin over ``role_order``
when neither is present.

No existing single-agent files are modified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from bench_common.config import settings
from bench_common.core.binding_vow import BindingVow
from bench_common.core.run import AgentConfig, Episode, TraceEvent
from bench_common.runtime.env_client import HttpEnvClient
from bench_common.runtime.inference import InferenceRouter
from bench_common.storage.trace_store import TraceStore
from bench_common.techniques.memory import EpisodicMemoryTechnique

log = structlog.get_logger()

_DEFAULT_PLATFORM_MAX_STEPS = 35


@dataclass
class RoleState:
    """All mutable per-agent state for one named role within an episode."""

    config: AgentConfig
    inference: InferenceRouter
    memory: EpisodicMemoryTechnique
    window_size: int = 10
    env_system_prompt: str | None = None
    total_tokens: int = field(default=0)


def _resolve_active_role(
    obs_data: Any,
    info: dict[str, Any],
    role_order: list[str],
    step: int,
) -> str:
    """Return the role that should act on this step.

    Priority:
      1. ``info["active_role"]`` — env explicitly says who acts next (post-step).
      2. ``obs_data["active_role"]`` — env encodes it in the observation (post-reset).
      3. Round-robin over ``role_order`` as a fallback.
    """
    if "active_role" in info:
        return str(info["active_role"])
    if isinstance(obs_data, dict) and "active_role" in obs_data:
        return str(obs_data["active_role"])
    return role_order[step % len(role_order)]


class MultiAgentLoop:
    """
    Runs one episode with multiple named agents taking turns.

    Each role has isolated inference context and its own sliding-window memory,
    but they interact with the same environment instance so shared game state
    (e.g. a chess board) is mediated entirely by the env adapter.
    """

    def __init__(
        self,
        binding_vow: BindingVow,
        roles: dict[str, RoleState],
        role_order: list[str],
        trace: TraceStore,
    ) -> None:
        self.vow = binding_vow
        self.roles = roles
        self.role_order = role_order
        self.trace = trace

    async def run_episode(
        self,
        env_client: HttpEnvClient,
        episode_id: str,
        seed: int | None,
    ) -> Episode:
        episode = Episode(
            id=episode_id,
            run_id="",
            seed=seed,
            status="running",
            started_at=datetime.utcnow(),
        )

        await self.trace.append(
            TraceEvent(
                episode_id=episode_id,
                step=0,
                event_type="episode_start",
                payload={"seed": seed, "roles": self.role_order},
            )
        )

        for _role, state in self.roles.items():
            await state.memory.on_episode_start(episode_id, {"window_size": state.window_size})

        obs = await env_client.reset(episode_id=episode_id, seed=seed)
        if obs.system_prompt is not None:
            for state in self.roles.values():
                state.env_system_prompt = obs.system_prompt

        # Determine first actor: step=0 → round-robin gives role_order[0]
        info: dict[str, Any] = {}
        active_role = _resolve_active_role(obs.data, info, self.role_order, step=0)

        step = 0
        total_reward = 0.0
        result = None
        declared_max = self.vow.episode.max_steps
        platform_cap = (
            settings.max_episode_steps
            if settings.max_episode_steps > 0
            else _DEFAULT_PLATFORM_MAX_STEPS
        )
        max_steps = min(declared_max, platform_cap) if declared_max is not None else platform_cap
        token_budget = settings.max_tokens_per_episode
        terminal_info: dict[str, Any] | None = None

        try:
            while True:
                step += 1

                state = self.roles.get(active_role)
                if state is None:
                    log.warning(
                        "multi_agent_unknown_role",
                        active_role=active_role,
                        known=list(self.roles),
                    )
                    # fall back to first role rather than crashing the episode
                    active_role = self.role_order[0]
                    state = self.roles[active_role]

                # Each agent sees its own history prepended to the observation.
                extra_context = await state.memory.before_action(obs, {})
                extra_context["Active Role"] = active_role

                await self.trace.append(
                    TraceEvent(
                        episode_id=episode_id,
                        step=step,
                        event_type="observation",
                        payload={
                            "role": active_role,
                            "phase": "before_agent",
                            "data": obs.data,
                            "content_type": obs.content_type,
                        },
                    )
                )

                decision = await state.inference.decide(
                    observation=obs,
                    binding_vow=self.vow,
                    agent_config=state.config,
                    extra_context=extra_context,
                    step=step,
                    env_system_prompt=state.env_system_prompt,
                )

                state.total_tokens += decision.total_tokens
                all_tokens = sum(s.total_tokens for s in self.roles.values())
                if token_budget > 0 and all_tokens > token_budget:
                    log.warning(
                        "multi_agent_token_budget_exceeded",
                        episode_id=episode_id,
                        all_tokens=all_tokens,
                        budget=token_budget,
                        step=step,
                    )
                    episode.status = "failed"
                    terminal_info = {
                        "reason": "token_budget_exceeded",
                        "total_tokens": all_tokens,
                        "budget": token_budget,
                    }
                    break

                if decision.reasoning_text:
                    await self.trace.append(
                        TraceEvent(
                            episode_id=episode_id,
                            step=step,
                            event_type="model_call",
                            payload={"role": active_role, "text": decision.reasoning_text},
                        )
                    )

                await self.trace.append(
                    TraceEvent(
                        episode_id=episode_id,
                        step=step,
                        event_type="action",
                        payload={"role": active_role, "action": decision.action},
                    )
                )

                result = await env_client.step(episode_id=episode_id, action=decision.action)
                info = result.info
                total_reward += result.reward

                await self.trace.append(
                    TraceEvent(
                        episode_id=episode_id,
                        step=step,
                        event_type="step_result",
                        payload={
                            "role": active_role,
                            "reward": result.reward,
                            "terminated": result.terminated,
                            "truncated": result.truncated,
                            "info": info,
                        },
                    )
                )

                # Only the acting agent's memory records this step.
                await state.memory.after_action(decision.action, result, {})

                if result.system_prompt is not None:
                    state.env_system_prompt = result.system_prompt

                if result.terminated or result.truncated:
                    episode.status = "completed"
                    break

                if step >= max_steps:
                    episode.status = "truncated"
                    terminal_info = {"reason": "step_limit", "max_steps": max_steps}
                    break

                obs = result.observation
                active_role = _resolve_active_role(obs.data, info, self.role_order, step)

        finally:
            try:
                await env_client.close(episode_id=episode_id)
            except Exception:
                log.warning("env_close_failed", episode_id=episode_id)

        if terminal_info is None:
            terminal_info = result.info if result else {}

        all_tokens = sum(s.total_tokens for s in self.roles.values())
        terminal_info = {
            **terminal_info,
            "total_tokens": all_tokens,
            "tokens_per_role": {r: s.total_tokens for r, s in self.roles.items()},
        }

        for state in self.roles.values():
            await state.memory.on_episode_end(episode_id, terminal_info)

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
            "multi_agent_episode_done",
            episode_id=episode_id,
            steps=step,
            total_reward=total_reward,
            status=episode.status,
        )
        return episode
