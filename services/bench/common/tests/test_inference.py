"""Inference router helpers for Gemini provider keys and model IDs."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from bench_common.core.binding_vow import BindingVow
from bench_common.runtime.env_client import Observation
from bench_common.runtime.inference import (
    InferenceRouter,
    StructuredOutputError,
    _resolve_google_api_key,
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


def test_structured_openai_requires_action_field() -> None:
    router = InferenceRouter()

    with pytest.raises(StructuredOutputError, match="action"):
        router._extract_structured_action(_response_with_content('{"move": "left"}'), "openai")


def test_structured_openai_extracts_action_field() -> None:
    router = InferenceRouter()

    action, reasoning = router._extract_structured_action(
        _response_with_content('{"action": {"move": "left"}}'),
        "openai",
    )

    assert action == {"move": "left"}
    assert reasoning == ""


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


def test_image_content_strips_data_url_for_anthropic_base64_source() -> None:
    router = InferenceRouter(allow_any_model=True)
    content = router._build_user_content(
        Observation(data="data:image/png;base64,AAEC", content_type="image/png"),
        step=4,
        provider="anthropic",
    )

    assert content == [
        {"type": "text", "text": "[Step 4]"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "AAEC",
            },
        },
    ]
