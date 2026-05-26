"""Validate mesocosm init benchanything.json without API register fields."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from swecc_mesocosm.validation import validate_benchmark_config

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE = (
    _REPO_ROOT
    / "services"
    / "bench"
    / "common"
    / "bench_common"
    / "cli"
    / "templates"
    / "benchanything.json"
)


def test_init_template_validates_as_manifest() -> None:
    payload = json.loads(_TEMPLATE.read_text(encoding="utf-8"))
    result = validate_benchmark_config(payload)
    assert result["ok"] is True
    assert result.get("schema") == "benchanything_manifest"


def test_register_payload_still_requires_owner_and_endpoint(
    minimal_domain_payload: dict[str, object],
) -> None:
    result = validate_benchmark_config(minimal_domain_payload)
    assert result["ok"] is True
    assert "schema" not in result
