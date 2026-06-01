"""Format bench run / episode terminal status for CLI and tooling."""

from __future__ import annotations

from typing import Any

RUN_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
RUN_FAILURE_STATUSES = frozenset({"failed", "cancelled"})
EPISODE_FAILURE_STATUSES = frozenset({"failed", "cancelled", "timeout"})
EPISODE_TRUNCATED_STATUSES = frozenset({"truncated"})

# Stable codes from bench-api → short human labels for CLI / docs.
REASON_LABELS: dict[str, str] = {
    "user_cancelled": "Cancelled by user",
    "task_cancelled": "Run task cancelled",
    "domain_missing": "Domain no longer exists",
    "no_episodes": "No episodes were recorded",
    "insufficient_scoreable_episodes": "Too few episodes finished successfully",
    "execute_run_error": "Run execution error",
    "stale_run_timeout": "Run timed out (stale)",
    "bench_api_restart": "Interrupted by platform restart",
    "manual_reap": "Marked failed by operator",
    "stale_orphan": "Stranded run cleaned up",
    "unknown_failure": "Run failed (reason unknown)",
    "run_cancelled": "Cancelled while running",
    "task_cancelled_episode": "Episode task cancelled",
    "episode_error": "Episode error",
    "no_env_url": "No environment URL configured",
    "step_limit": "Step limit reached",
    "wall_time_limit": "Wall-clock time limit reached",
    "token_budget_exceeded": "Token budget exceeded",
}


def reason_label(code: str | None) -> str:
    if not code:
        return "Unknown"
    return REASON_LABELS.get(code, code.replace("_", " ").capitalize())


def terminal_info_reason(episode: dict[str, Any]) -> str | None:
    info = episode.get("terminal_info") or {}
    if not isinstance(info, dict):
        return None
    reason = info.get("reason")
    if isinstance(reason, str) and reason:
        return reason
    if episode.get("status") == "failed" and info.get("error"):
        return "episode_error"
    return None


def episode_status_line(episode: dict[str, Any]) -> str:
    status = str(episode.get("status") or "unknown")
    ep_id = episode.get("id", "?")
    seed = episode.get("seed")
    seed_bit = f" seed={seed}" if seed is not None else ""
    reason = terminal_info_reason(episode)
    line = f"  episode {ep_id}{seed_bit}: {status}"
    if reason:
        line += f" — {reason_label(reason)}"
    info = episode.get("terminal_info") or {}
    if isinstance(info, dict):
        if info.get("error") and reason != "episode_error":
            line += f" ({info['error']})"
        elif info.get("detail") and status in RUN_FAILURE_STATUSES:
            line += f" ({info['detail']})"
        elif info.get("max_steps") and reason == "step_limit":
            line += f" (max_steps={info.get('max_steps')})"
    return line


def run_status_summary(run: dict[str, Any], episodes: list[dict[str, Any]] | None = None) -> list[str]:
    """Plain-text lines describing run terminal state."""
    lines: list[str] = []
    status = str(run.get("status") or "unknown")
    lines.append(f"run {run.get('id', '?')}: {status}")

    reason = run.get("status_reason")
    detail = run.get("status_detail") or {}
    if reason:
        lines.append(f"  reason: {reason_label(str(reason))} ({reason})")
    if isinstance(detail, dict) and detail:
        outcomes = detail.get("episode_outcomes")
        if isinstance(outcomes, dict):
            parts = [f"{k}={v}" for k, v in sorted(outcomes.items()) if v]
            if parts:
                lines.append(f"  episodes: {', '.join(parts)}")
        for key in ("failure_reasons", "truncation_reasons", "cancellation_reasons"):
            vals = detail.get(key)
            if isinstance(vals, list) and vals:
                labels = [reason_label(str(v)) for v in vals]
                lines.append(f"  {key.replace('_', ' ')}: {', '.join(labels)}")

    if episodes:
        for ep in episodes:
            lines.append(episode_status_line(ep))
    return lines


def is_run_terminal(status: str | None) -> bool:
    return status in RUN_TERMINAL_STATUSES
