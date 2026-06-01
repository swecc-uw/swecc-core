"""Tests for run status formatting."""

from __future__ import annotations

from swecc_mesocosm.run_status import reason_label, run_status_summary


def test_reason_label_known_code() -> None:
    assert reason_label("step_limit") == "Step limit reached"


def test_reason_label_unknown_code() -> None:
    assert reason_label("custom_reason") == "Custom reason"


def test_run_status_summary_includes_reason_and_episodes() -> None:
    run = {
        "id": "run-1",
        "status": "failed",
        "status_reason": "insufficient_scoreable_episodes",
        "status_detail": {
            "episode_outcomes": {"failed": 2, "truncated": 1},
            "failure_reasons": ["episode_error"],
            "truncation_reasons": ["step_limit"],
        },
    }
    episodes = [
        {
            "id": "e1",
            "seed": 0,
            "status": "truncated",
            "terminal_info": {"reason": "step_limit", "max_steps": 35},
        },
    ]
    lines = run_status_summary(run, episodes)
    text = "\n".join(lines)
    assert "insufficient_scoreable_episodes" in text
    assert "Step limit reached" in text
    assert "episode e1" in text
