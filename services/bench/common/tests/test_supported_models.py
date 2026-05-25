"""LiteLLM provider resolution for bench model catalog."""

from __future__ import annotations

import pytest
from bench_common.model_catalog import ALLOWED_MODELS, FULL_BENCH_MODELS
from litellm import get_llm_provider


@pytest.mark.parametrize("model_id", ALLOWED_MODELS)
def test_litellm_recognizes_allowed_model(model_id: str) -> None:
    custom_llm_provider, model, *_rest = get_llm_provider(model_id)
    assert custom_llm_provider
    assert model


def test_full_bench_gemini_uses_gemini_prefix_not_google() -> None:
    gemini_models = [m for m in FULL_BENCH_MODELS if "gemini" in m]
    assert len(gemini_models) == 1
    assert gemini_models[0].startswith("gemini/")
    with pytest.raises(Exception):
        get_llm_provider("google/gemini-2.0-flash")
