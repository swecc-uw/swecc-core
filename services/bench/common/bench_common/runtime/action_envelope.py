"""Normalize structured model actions before env /step."""

from __future__ import annotations

from typing import Any

from bench_common.core.binding_vow import CompositeSpace, SpaceSpec, SpaceType


def unwrap_action_envelope(action: Any) -> Any:
    """Strip nested ``{"action": ...}`` wrappers from structured model output."""
    while isinstance(action, dict) and len(action) == 1 and "action" in action:
        action = action["action"]
    return action


def _discrete_from_dict(payload: dict[str, Any], enum_values: list[str]) -> str | None:
    for val in payload.values():
        if isinstance(val, str):
            for allowed in enum_values:
                if val.upper() == allowed.upper():
                    return allowed
    return None


def finalize_resolved_action(action: Any, space: SpaceSpec | CompositeSpace) -> Any:
    """Return an env-ready action after structured-output parsing."""
    action = unwrap_action_envelope(action)
    if (
        isinstance(space, SpaceSpec)
        and space.type == SpaceType.DISCRETE
        and space.enum_values
        and isinstance(action, dict)
    ):
        found = _discrete_from_dict(action, space.enum_values)
        if found is not None:
            return found
    return action
