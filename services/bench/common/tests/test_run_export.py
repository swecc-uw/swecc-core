"""Tests for run export / replay shaping."""

from datetime import datetime

from bench_common.core.run import TraceEvent
from bench_common.export.replay import build_replay_turns


def test_build_replay_turns_includes_reasoning_and_action():
    ep = "ep-1"
    events = [
        TraceEvent(
            episode_id=ep,
            step=0,
            event_type="observation",
            payload={"data": {"board": []}},
        ),
        TraceEvent(
            episode_id=ep,
            step=1,
            event_type="model_call",
            payload={
                "text": "Two signals. Size a core position before CPI.",
                "model": "gemini/gemini-2.0-flash",
            },
        ),
        TraceEvent(
            episode_id=ep,
            step=1,
            event_type="action",
            payload={"action": {"side": "buy", "size": 10}},
        ),
        TraceEvent(
            episode_id=ep,
            step=1,
            event_type="step_result",
            payload={"reward": 0.5, "terminated": False, "truncated": False, "info": {}},
        ),
    ]
    turns = build_replay_turns(events)
    assert len(turns) == 1
    assert turns[0]["step"] == 1
    assert "Two signals" in turns[0]["reasoning"]
    assert turns[0]["action"] == {"side": "buy", "size": 10}
    assert turns[0]["reward"] == 0.5


def test_build_replay_turns_splits_board_phases():
    ep = "ep-2"
    events = [
        TraceEvent(
            episode_id=ep,
            step=1,
            event_type="observation",
            payload={"phase": "before_agent", "data": {"board": [""] * 9}},
        ),
        TraceEvent(
            episode_id=ep,
            step=1,
            event_type="observation",
            payload={"phase": "after_env", "data": {"board": ["X"] + [""] * 8}},
        ),
    ]
    turns = build_replay_turns(events)
    assert turns[0]["board_before"]["board"] == [""] * 9
    assert turns[0]["board_after"]["board"][0] == "X"
