from __future__ import annotations

import math

import pytest
from bench_common.env_sdk.server import _info_payload, _jsonable_payload, _reward_payload


def test_jsonable_payload_base64_encodes_bytes_for_json_transport() -> None:
    assert _jsonable_payload(b"\x00\x01\x02") == "AAEC"


def test_info_payload_preserves_parseable_nested_values() -> None:
    payload = _info_payload({1: {"won": True, "path": ["a", "b"]}})
    assert payload == {"1": {"won": True, "path": ["a", "b"]}}


def test_reward_payload_rejects_non_finite_rewards() -> None:
    assert _reward_payload(2) == 2.0
    for reward in (math.inf, -math.inf, math.nan):
        with pytest.raises(ValueError, match="finite"):
            _reward_payload(reward)
