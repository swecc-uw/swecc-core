from __future__ import annotations

import math

import pytest
from bench_common.runtime.env_client import (
    _parse_bool,
    _parse_info,
    _parse_observation_body,
    _parse_reward,
)


def test_parse_observation_accepts_scalar_payload() -> None:
    obs = _parse_observation_body("plain text observation")
    assert obs.data == "plain text observation"
    assert obs.content_type == "application/json"
    assert obs.system_prompt is None


def test_parse_observation_accepts_wrapped_image_payload() -> None:
    obs = _parse_observation_body(
        {
            "data": "iVBORw0KGgo=",
            "content_type": "image/png",
            "system_prompt": "Inspect the image.",
        }
    )
    assert obs.data == "iVBORw0KGgo="
    assert obs.content_type == "image/png"
    assert obs.system_prompt == "Inspect the image."


def test_parse_bool_does_not_treat_false_string_as_true() -> None:
    assert _parse_bool("false", "terminated") is False
    assert _parse_bool("0", "terminated") is False
    assert _parse_bool("true", "terminated") is True
    assert _parse_bool(1, "terminated") is True


def test_parse_bool_rejects_ambiguous_values() -> None:
    with pytest.raises(ValueError, match="terminated"):
        _parse_bool("eventually", "terminated")


def test_parse_reward_requires_finite_number() -> None:
    assert _parse_reward("3.5") == 3.5
    for bad in (math.inf, -math.inf, math.nan, "not-a-number"):
        with pytest.raises(ValueError, match="reward"):
            _parse_reward(bad)


def test_parse_info_preserves_nested_json_values_with_string_keys() -> None:
    info = _parse_info(
        {
            7: {"cells": [1, 2, 3], "success": False},
            "score_breakdown": {"exact": 1.0},
        }
    )
    assert info == {
        "7": {"cells": [1, 2, 3], "success": False},
        "score_breakdown": {"exact": 1.0},
    }


def test_parse_info_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="info"):
        _parse_info(["not", "an", "object"])
