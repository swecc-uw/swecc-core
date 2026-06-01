from __future__ import annotations

import pytest
from bench_common.core.binding_vow import SpaceSpec, SpaceType
from bench_common.runtime.action_envelope import finalize_resolved_action, unwrap_action_envelope
from bench_common.runtime.inference import _resolve_structured_action


def test_unwrap_action_envelope_strips_nested_wrappers() -> None:
    assert unwrap_action_envelope({"action": {"action": "E"}}) == "E"
    assert unwrap_action_envelope({"action": "N"}) == "N"


def test_finalize_resolved_action_discrete_from_double_wrapped_payload() -> None:
    space = SpaceSpec(type=SpaceType.DISCRETE, enum_values=["N", "S", "E", "W"])
    assert finalize_resolved_action({"action": {"action": "E"}}, space) == "E"


def test_resolve_structured_action_discrete_unwraps_double_wrapped_action() -> None:
    space = SpaceSpec(type=SpaceType.DISCRETE, enum_values=["N", "S", "E", "W"])

    action, _ = _resolve_structured_action({"action": {"action": "E"}}, space)
    assert action == "E"


def test_resolve_structured_action_json_keeps_inner_object() -> None:
    space = SpaceSpec(type=SpaceType.JSON)

    action, _ = _resolve_structured_action({"action": {"move": "left"}}, space)
    assert action == {"move": "left"}


def test_unwrap_action_envelope_does_not_strip_composite_payload() -> None:
    payload = {"direction": "N", "magnitude": 0.5}
    assert unwrap_action_envelope(payload) == payload
