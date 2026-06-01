"""Tests for run/episode terminal status helpers."""

from __future__ import annotations

from bench_common.core.run import Episode, Run, RunConfig
from bench_common.core.status import (
    EPISODE_CANCELLED_RUN,
    EPISODE_ERROR,
    RUN_CANCELLED_USER,
    RUN_FAILED_INSUFFICIENT_SCOREABLE,
    apply_run_terminal,
    resolve_run_status,
    resolve_run_status_from_summary,
    summarize_episodes,
)


def _run(*, status: str = "failed", reason: str | None = None) -> Run:
    return Run(
        id="run-1",
        config=RunConfig(
            domain_id="d1",
            binding_vow_version="1.0.0",
            agent_config={"model": "openai/gpt-4o"},
        ),
        requester_id="u1",
        status=status,
        status_reason=reason,
    )


def test_summarize_episodes_collects_reasons() -> None:
    episodes = [
        Episode(id="e1", run_id="run-1", status="truncated", terminal_info={"reason": "step_limit"}),
        Episode(id="e2", run_id="run-1", status="failed", terminal_info={"reason": "episode_error", "error": "boom"}),
        Episode(id="e3", run_id="run-1", status="cancelled", terminal_info={"reason": EPISODE_CANCELLED_RUN}),
    ]
    summary = summarize_episodes(episodes)
    assert summary.truncated_count == 1
    assert summary.failed_count == 1
    assert summary.cancelled_count == 1
    assert summary.truncation_reasons == ("step_limit",)
    assert summary.failure_reasons == (EPISODE_ERROR,)
    assert summary.cancellation_reasons == (EPISODE_CANCELLED_RUN,)


def test_apply_run_terminal_persists_reason() -> None:
    run = apply_run_terminal(_run(status="running"), status="failed", reason="stale_run_timeout", detail={"detail": "x"})
    assert run.status == "failed"
    assert run.status_reason == "stale_run_timeout"
    assert run.status_detail == {"detail": "x"}


def test_resolve_run_status_from_summary_cancelled() -> None:
    run = _run(status="cancelled")
    summary = summarize_episodes([
        Episode(id="e1", run_id="run-1", status="cancelled", terminal_info={"reason": EPISODE_CANCELLED_RUN}),
    ])
    reason, detail = resolve_run_status_from_summary(run, summary)
    assert reason == RUN_CANCELLED_USER
    assert detail["episode_outcomes"]["cancelled"] == 1


def test_resolve_run_status_infers_insufficient_scoreable() -> None:
    run = _run(status="failed")
    episodes = [
        Episode(id="e1", run_id="run-1", status="failed", terminal_info={"reason": EPISODE_ERROR, "error": "x"}),
    ]
    reason, detail = resolve_run_status(run, episodes=episodes)
    assert reason == RUN_FAILED_INSUFFICIENT_SCOREABLE
    assert detail["primary_episode_reason"] == EPISODE_ERROR
