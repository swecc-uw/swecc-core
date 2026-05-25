"""Inference router helpers for Gemini provider keys and model IDs."""

from __future__ import annotations

import os

import pytest

from bench_common.runtime.inference import _resolve_google_api_key, normalize_model_id


def test_normalize_model_id_maps_google_prefix_to_gemini() -> None:
    assert normalize_model_id("google/gemini-2.0-flash") == "gemini/gemini-2.0-flash"
    assert normalize_model_id("gemini/gemini-3.1-flash-lite") == "gemini/gemini-3.1-flash-lite"


def test_resolve_google_api_key_prefers_real_key_over_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "placeholder")
    monkeypatch.setenv("GEMINI_API_KEY", "real-gemini-key")
    assert _resolve_google_api_key() == "real-gemini-key"


def test_resolve_google_api_key_uses_google_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "real-google-key")
    monkeypatch.setenv("GEMINI_API_KEY", "real-gemini-key")
    assert _resolve_google_api_key() == "real-google-key"


def test_resolve_google_api_key_empty_when_only_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    assert _resolve_google_api_key() is None
