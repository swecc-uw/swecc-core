from __future__ import annotations

import json
from pathlib import Path

import pytest

from swecc_mesocosm import validation
from swecc_mesocosm.infer import build_domain_payload


def _minimal_payload() -> dict:
    return build_domain_payload(
        benchmark_id="demo",
        name="Demo",
        owner_id="owner",
        description="trivia quiz",
        env_url="https://example.com/env",
    )


def test_validate_benchmark_config_ok() -> None:
    result = validation.validate_benchmark_config(_minimal_payload())
    assert result["ok"] is True
    assert result["issues"] == []


def test_validate_benchmark_config_missing_field() -> None:
    payload = _minimal_payload()
    del payload["name"]
    result = validation.validate_benchmark_config(payload)
    assert result["ok"] is False
    assert any("name" in issue for issue in result["issues"])


def test_validate_benchmark_config_bad_primary_metric() -> None:
    payload = _minimal_payload()
    payload["scoring"]["primary_metric"] = "nonexistent_metric"
    result = validation.validate_benchmark_config(payload)
    assert result["ok"] is False
    assert any("primary_metric" in issue for issue in result["issues"])


def test_validate_benchmark_config_disallowed_model_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    policy = tmp_path / "constraints.json"
    policy.write_text(
        json.dumps(
            {
                "rules_version": "test",
                "required_register_fields": ["id", "name"],
                "allowed_model_prefixes": ["openai/"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(validation.settings, "policy_dir", tmp_path)
    payload = {"id": "x", "name": "y", "inferred_agent": {"model": "ollama/llama3"}}
    result = validation.validate_benchmark_config(payload)
    assert result["ok"] is False
    assert any("allowed_model_prefixes" in issue for issue in result["issues"])


def test_load_constraints_invalid_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    policy = tmp_path / "constraints.json"
    policy.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(validation.settings, "policy_dir", tmp_path)
    loaded = validation.load_constraints()
    assert "error" in loaded
    assert "invalid JSON" in loaded["error"]
