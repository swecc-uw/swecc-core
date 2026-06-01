"""Run/episode terminal status helpers — reason codes and outcome aggregation."""

from __future__ import annotations

from collections import Counter
from typing import Any, NamedTuple

from bench_common.core.run import Episode, Run

# Run-level reason codes (machine-readable; stable for UI + automation).
RUN_CANCELLED_USER = "user_cancelled"
RUN_CANCELLED_TASK = "task_cancelled"
RUN_FAILED_DOMAIN_MISSING = "domain_missing"
RUN_FAILED_NO_EPISODES = "no_episodes"
RUN_FAILED_INSUFFICIENT_SCOREABLE = "insufficient_scoreable_episodes"
RUN_FAILED_EXECUTE_ERROR = "execute_run_error"
RUN_FAILED_STALE = "stale_run_timeout"
RUN_FAILED_ORPHAN = "bench_api_restart"
RUN_FAILED_MANUAL_REAP = "manual_reap"
RUN_FAILED_STALE_ORPHAN = "stale_orphan"

# Episode-level reason codes surfaced in terminal_info["reason"].
EPISODE_CANCELLED_RUN = "run_cancelled"
EPISODE_CANCELLED_TASK = "task_cancelled"
EPISODE_ERROR = "episode_error"
EPISODE_NO_ENV_URL = "no_env_url"


class EpisodeOutcomeSummary(NamedTuple):
    completed_count: int = 0
    failed_count: int = 0
    truncated_count: int = 0
    cancelled_count: int = 0
    timeout_count: int = 0
    avg_reward: float | None = None
    failure_reasons: tuple[str, ...] = ()
    truncation_reasons: tuple[str, ...] = ()
    cancellation_reasons: tuple[str, ...] = ()


def _terminal_reason(ep: Episode) -> str | None:
    info = ep.terminal_info or {}
    reason = info.get("reason")
    if isinstance(reason, str) and reason:
        return reason
    if ep.status == "failed" and info.get("error"):
        return EPISODE_ERROR
    return None


def summarize_episodes(episodes: list[Episode]) -> EpisodeOutcomeSummary:
    completed = failed = truncated = cancelled = timeout = 0
    failure_reasons: Counter[str] = Counter()
    truncation_reasons: Counter[str] = Counter()
    cancellation_reasons: Counter[str] = Counter()
    rewards: list[float] = []

    for ep in episodes:
        if ep.status == "completed":
            completed += 1
            rewards.append(ep.total_reward)
        elif ep.status == "truncated":
            truncated += 1
            rewards.append(ep.total_reward)
            reason = _terminal_reason(ep) or "step_limit"
            truncation_reasons[reason] += 1
        elif ep.status == "timeout":
            timeout += 1
            failure_reasons[_terminal_reason(ep) or "wall_time_limit"] += 1
        elif ep.status == "failed":
            failed += 1
            failure_reasons[_terminal_reason(ep) or EPISODE_ERROR] += 1
        elif ep.status == "cancelled":
            cancelled += 1
            cancellation_reasons[_terminal_reason(ep) or EPISODE_CANCELLED_RUN] += 1

    avg_reward = sum(rewards) / len(rewards) if rewards else None
    return EpisodeOutcomeSummary(
        completed_count=completed,
        failed_count=failed + timeout,
        truncated_count=truncated,
        cancelled_count=cancelled,
        timeout_count=timeout,
        avg_reward=avg_reward,
        failure_reasons=tuple(r for r, _ in failure_reasons.most_common(3)),
        truncation_reasons=tuple(r for r, _ in truncation_reasons.most_common(3)),
        cancellation_reasons=tuple(r for r, _ in cancellation_reasons.most_common(3)),
    )


def apply_run_terminal(
    run: Run,
    *,
    status: str,
    reason: str,
    detail: dict[str, Any] | None = None,
) -> Run:
    """Return a run copy with terminal status + persisted reason metadata."""
    updates: dict[str, Any] = {
        "status": status,
        "status_reason": reason,
        "status_detail": detail or {},
    }
    return run.model_copy(update=updates)


def resolve_run_status_from_summary(
    run: Run,
    summary: EpisodeOutcomeSummary,
) -> tuple[str | None, dict[str, Any]]:
    """Like resolve_run_status but uses pre-aggregated episode counts."""
    if run.status_reason:
        return run.status_reason, dict(run.status_detail or {})
    if run.status not in ("failed", "cancelled"):
        return None, {}

    detail: dict[str, Any] = {
        "episode_outcomes": {
            "completed": summary.completed_count,
            "failed": summary.failed_count,
            "truncated": summary.truncated_count,
            "cancelled": summary.cancelled_count,
            "timeout": summary.timeout_count,
        },
    }
    if summary.failure_reasons:
        detail["failure_reasons"] = list(summary.failure_reasons)
    if summary.truncation_reasons:
        detail["truncation_reasons"] = list(summary.truncation_reasons)
    if summary.cancellation_reasons:
        detail["cancellation_reasons"] = list(summary.cancellation_reasons)

    if run.status == "cancelled":
        if EPISODE_CANCELLED_TASK in summary.cancellation_reasons:
            return RUN_CANCELLED_TASK, detail
        return RUN_CANCELLED_USER, detail

    total = sum(detail["episode_outcomes"].values())
    if total and summary.completed_count + summary.truncated_count == 0:
        if summary.failure_reasons:
            detail["primary_episode_reason"] = summary.failure_reasons[0]
        return RUN_FAILED_INSUFFICIENT_SCOREABLE, detail

    return "unknown_failure", detail


def resolve_run_status(
    run: Run,
    *,
    episodes: list[Episode] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Return (status_reason, status_detail) for API surfaces."""
    if episodes is not None:
        return resolve_run_status_from_summary(run, summarize_episodes(episodes))
    if run.status_reason:
        return run.status_reason, dict(run.status_detail or {})
    if run.status not in ("failed", "cancelled"):
        return None, {}
    return None, {}
