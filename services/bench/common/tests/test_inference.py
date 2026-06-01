"""Inference router helpers for Gemini provider keys and model IDs."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest
from bench_common.core.binding_vow import BindingVow
from bench_common.runtime.env_client import Observation
from bench_common.runtime.inference import (
    InferenceRouter,
    StructuredOutputError,
    _provider_action_schema,
    _resolve_google_api_key,
    _resolve_structured_action,
    _uses_action_envelope,
    normalize_model_id,
)


def test_normalize_model_id_maps_google_prefix_to_gemini() -> None:
    assert normalize_model_id("google/gemini-3.1-flash-lite") == "gemini/gemini-3.1-flash-lite"
    assert normalize_model_id("gemini/gemini-3.1-flash-lite") == "gemini/gemini-3.1-flash-lite"


def test_resolve_google_api_key_prefers_real_key_over_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "placeholder")
    monkeypatch.setenv("GEMINI_API_KEY", "real-gemini-key")
    assert _resolve_google_api_key() == "real-gemini-key"


def test_resolve_google_api_key_uses_google_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "real-google-key")
    monkeypatch.setenv("GEMINI_API_KEY", "real-gemini-key")
    assert _resolve_google_api_key() == "real-google-key"


def test_resolve_google_api_key_empty_when_only_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    assert _resolve_google_api_key() is None


def _vow_for_action_space(action_space: dict) -> BindingVow:
    return BindingVow(
        id="parse-test-vow",
        version="1.0.0",
        domain_id="parse-test",
        tier="tier1",
        observation_space={"type": "text", "description": "state"},
        action_space=action_space,
        reward={"type": "scalar", "description": "reward"},
        episode={"max_steps": 1, "supports_seed": True},
        techniques=[],
    )


def test_parse_json_action_after_reasoning_text() -> None:
    router = InferenceRouter(allow_any_model=True)
    vow = _vow_for_action_space({"type": "json"})

    action = router._parse_action('I will choose carefully.\n{"move": "left", "power": 2}', vow)

    assert action == {"move": "left", "power": 2}


def test_parse_json_action_from_markdown_fence() -> None:
    router = InferenceRouter(allow_any_model=True)
    vow = _vow_for_action_space({"type": "json"})

    action = router._parse_action('```json\n{"answer": ["a", "b"]}\n```', vow)

    assert action == {"answer": ["a", "b"]}


def test_parse_composite_action_as_json_object() -> None:
    router = InferenceRouter(allow_any_model=True)
    vow = _vow_for_action_space(
        {
            "fields": {
                "direction": {"type": "discrete", "enum_values": ["left", "right"]},
                "magnitude": {"type": "continuous"},
            }
        }
    )

    action = router._parse_action('{"direction": "right", "magnitude": 0.75}', vow)

    assert action == {"direction": "right", "magnitude": 0.75}


def test_parse_continuous_action_as_number() -> None:
    router = InferenceRouter(allow_any_model=True)
    vow = _vow_for_action_space({"type": "continuous"})

    assert router._parse_action("0.125", vow) == 0.125
    assert router._parse_action("I choose -3.5e-2", vow) == -3.5e-2


def test_parse_continuous_action_keeps_ambiguous_text() -> None:
    router = InferenceRouter(allow_any_model=True)
    vow = _vow_for_action_space({"type": "continuous"})

    assert router._parse_action("between 1 and 2", vow) == "between 1 and 2"


def _response_with_content(content: str):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            )
        ]
    )


JENGA_ACTION_SPACE = {
    "type": "json",
    "schema_ref": (
        '{"type":"object","properties":{"context":{"type":"string"},'
        '"action":{"type":"object","properties":{"type":{"const":"Push"},'
        '"layer":{"type":"integer"}},"required":["type","layer"],'
        '"additionalProperties":false}},"required":["context","action"],'
        '"additionalProperties":false}'
    ),
    "description": "context plus Push action",
}


def test_provider_action_schema_skips_wrap_for_json_envelope() -> None:
    vow = _vow_for_action_space(JENGA_ACTION_SPACE)
    schema = _provider_action_schema(vow.action_space)

    assert _uses_action_envelope(vow.action_space)
    assert "context" in schema["properties"]
    assert schema["required"] == ["context", "action"]
    assert set(schema["properties"]) == {"context", "action"}


def test_provider_action_schema_wraps_discrete_space() -> None:
    vow = _vow_for_action_space({"type": "discrete", "enum_values": ["A", "B"]})
    schema = _provider_action_schema(vow.action_space)

    assert schema == {
        "type": "object",
        "properties": {"action": {"type": "string", "enum": ["A", "B"]}},
        "required": ["action"],
    }


def test_structured_openai_rejects_incomplete_json_envelope() -> None:
    router = InferenceRouter()
    vow = _vow_for_action_space(JENGA_ACTION_SPACE)

    with pytest.raises(StructuredOutputError, match="missing required envelope fields"):
        router._extract_structured_action(
            _response_with_content('{"context": "thinking only"}'),
            "openai",
            vow.action_space,
        )


def test_structured_openai_accepts_json_envelope_at_top_level() -> None:
    router = InferenceRouter()
    vow = _vow_for_action_space(JENGA_ACTION_SPACE)
    payload = {
        "context": "Block looks loose on layer 3.",
        "action": {"type": "Push", "layer": 3},
    }

    action, reasoning = router._extract_structured_action(
        _response_with_content(json.dumps(payload)),
        "openai",
        vow.action_space,
    )

    assert action == payload
    assert reasoning == "Block looks loose on layer 3."


def test_structured_openai_accepts_platform_wrapped_json_envelope() -> None:
    router = InferenceRouter()
    vow = _vow_for_action_space(JENGA_ACTION_SPACE)
    inner = {
        "context": "Switching camera.",
        "action": {"type": "Push", "layer": 2},
    }

    action, reasoning = router._extract_structured_action(
        _response_with_content(json.dumps({"action": inner})),
        "gemini",
        vow.action_space,
    )

    assert action == inner
    assert reasoning == "Switching camera."


def test_structured_openai_extracts_wrapped_simple_json_action() -> None:
    router = InferenceRouter()
    vow = _vow_for_action_space({"type": "json"})

    action, reasoning = router._extract_structured_action(
        _response_with_content('{"action": {"move": "left"}}'),
        "openai",
        vow.action_space,
    )

    assert action == {"move": "left"}
    assert reasoning == ""


def test_structured_openai_accepts_unwrapped_json_object() -> None:
    router = InferenceRouter()
    vow = _vow_for_action_space({"type": "json"})

    action, reasoning = router._extract_structured_action(
        _response_with_content('{"move": "left", "power": 2}'),
        "openai",
        vow.action_space,
    )

    assert action == {"move": "left", "power": 2}
    assert reasoning == ""


def test_structured_openai_accepts_composite_fields_at_top_level() -> None:
    router = InferenceRouter()
    vow = _vow_for_action_space(
        {
            "fields": {
                "direction": {"type": "discrete", "enum_values": ["left", "right"]},
                "magnitude": {"type": "continuous"},
            }
        }
    )

    action, reasoning = router._extract_structured_action(
        _response_with_content('{"direction": "right", "magnitude": 0.75}'),
        "openai",
        vow.action_space,
    )

    assert action == {"direction": "right", "magnitude": 0.75}
    assert reasoning == ""


def test_resolve_structured_action_discrete_from_wrapped_payload() -> None:
    space = _vow_for_action_space({"type": "discrete", "enum_values": ["A", "B", "C"]}).action_space

    action, _ = _resolve_structured_action({"action": "B"}, space)
    assert action == "B"


def test_resolve_structured_action_discrete_from_double_wrapped_payload() -> None:
    space = _vow_for_action_space(
        {"type": "discrete", "enum_values": ["N", "S", "E", "W"]}
    ).action_space

    action, _ = _resolve_structured_action({"action": {"action": "E"}}, space)
    assert action == "E"


def test_image_content_preserves_data_url_for_openai() -> None:
    router = InferenceRouter(allow_any_model=True)
    content = router._build_user_content(
        Observation(data="data:image/png;base64,AAEC", content_type="image/png"),
        step=4,
        provider="openai",
    )

    assert content == [
        {"type": "text", "text": "[Step 4]"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,AAEC", "detail": "auto"},
        },
    ]


def test_image_content_uses_openai_blocks_for_anthropic_via_litellm() -> None:
    """LiteLLM validates user messages as OpenAI chat completions before routing."""
    router = InferenceRouter(allow_any_model=True)
    content = router._build_user_content(
        Observation(data="data:image/png;base64,AAEC", content_type="image/png"),
        step=4,
        provider="anthropic",
    )

    assert content == [
        {"type": "text", "text": "[Step 4]"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,AAEC", "detail": "auto"},
        },
    ]
