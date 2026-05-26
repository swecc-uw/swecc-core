"""Build JSON export bundles from runs, episodes, and trace events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bench_common.core.run import Episode, Run, TraceEvent

EXPORT_SCHEMA_VERSION = "1"


def _observation_suborder(payload: dict[str, Any]) -> int:
    phase = payload.get("phase") or ""
    if phase == "start":
        return 0
    if phase == "before_agent":
        return 1
    if phase == "after_env":
        return 5
    return 1


def _event_sort_key(ev: TraceEvent) -> tuple[int, int, str]:
    if ev.event_type == "observation":
        sub = _observation_suborder(ev.payload or {})
        return (ev.step, sub, ev.event_type)
    order = {
        "episode_start": 0,
        "model_call": 2,
        "action": 3,
        "tool_call": 3,
        "technique_event": 3,
        "step_result": 4,
        "reward": 4,
        "episode_end": 99,
    }
    return (ev.step, order.get(ev.event_type, 50), ev.event_type)


def build_replay_turns(events: list[TraceEvent]) -> list[dict[str, Any]]:
    """
    Flatten trace events into showcase-friendly turns.

    Each turn (step >= 1) may include observation, reasoning (model text),
    action, and step_result fields.
    """
    by_step: dict[int, dict[str, Any]] = {}

    for ev in sorted(events, key=_event_sort_key):
        if ev.event_type == "episode_start":
            continue
        turn = by_step.setdefault(
            ev.step,
            {"step": ev.step, "timestamp": ev.timestamp.isoformat()},
        )
        payload = ev.payload or {}

        if ev.event_type == "observation":
            phase = payload.get("phase") or ("start" if ev.step == 0 else "before_agent")
            data = payload.get("data")
            if phase in ("start", "before_agent"):
                turn["board_before"] = data
                turn["observation"] = data
            elif phase == "after_env":
                turn["board_after"] = data
            else:
                turn["observation"] = data
            if payload.get("system_prompt"):
                turn["env_system_prompt"] = payload["system_prompt"]
            if isinstance(data, dict) and data.get("message"):
                turn["env_message"] = data.get("message")
        elif ev.event_type == "model_call":
            text = (payload.get("text") or "").strip()
            if text:
                turn["reasoning"] = text
            if payload.get("model"):
                turn["model"] = payload["model"]
        elif ev.event_type == "action":
            turn["action"] = payload.get("action")
        elif ev.event_type == "step_result":
            turn["reward"] = payload.get("reward")
            turn["terminated"] = payload.get("terminated")
            turn["truncated"] = payload.get("truncated")
            turn["info"] = payload.get("info")
            if payload.get("system_prompt"):
                turn["env_system_prompt"] = payload["system_prompt"]
        elif ev.event_type == "episode_end":
            turn["episode_end"] = {
                "total_reward": payload.get("total_reward"),
                "steps": payload.get("steps"),
                "status": payload.get("status"),
                "terminal_info": payload.get("terminal_info"),
            }

    return [by_step[k] for k in sorted(by_step) if k >= 1]


def build_run_export_dict(
    *,
    run: Run,
    episodes: list[Episode],
    traces_by_episode: dict[str, list[TraceEvent]],
    visibility: str | None = None,
    domain_name: str | None = None,
) -> dict[str, Any]:
    """Assemble the full export document returned by GET /v1/runs/{id}/export."""
    traces_serialized: dict[str, list[dict[str, Any]]] = {}
    replay: dict[str, list[dict[str, Any]]] = {}

    for ep in episodes:
        events = traces_by_episode.get(ep.id, [])
        traces_serialized[ep.id] = [
            e.model_dump(mode="json") for e in sorted(events, key=_event_sort_key)
        ]
        replay[ep.id] = build_replay_turns(events)

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "visibility": visibility,
        "domain_id": run.config.domain_id,
        "domain_name": domain_name,
        "binding_vow_version": run.config.binding_vow_version,
        "run": run.model_dump(mode="json"),
        "episodes": [e.model_dump(mode="json") for e in episodes],
        "traces": traces_serialized,
        "replay": replay,
    }
