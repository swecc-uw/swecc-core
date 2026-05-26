from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from swecc_mesocosm.settings import settings


def _constraints_path() -> Path:
    return settings.policy_dir / "constraints.json"


def load_constraints() -> dict[str, Any]:
    p = _constraints_path()
    if not p.is_file():
        return {"rules_version": "0", "error": f"missing {p}"}
    try:
        return cast(dict[str, Any], json.loads(p.read_text(encoding="utf-8")))
    except json.JSONDecodeError as e:
        return {"rules_version": "0", "error": f"invalid JSON in {p}: {e}"}


_MANIFEST_REQUIRED_KEYS = ("adapter", "name", "binding_vow", "scoring")


def _is_benchanything_manifest(payload: dict[str, Any]) -> bool:
    """True for mesocosm init benchanything.json (local manifest, not API register body)."""
    if payload.get("adapter"):
        return True
    register_fields = {"owner_id", "endpoint"}
    has_register = any(k in payload for k in register_fields)
    return "binding_vow" in payload and "scoring" in payload and not has_register


def _validate_manifest_scoring_and_vow(
    domain_payload: dict[str, Any],
    issues: list[str],
    fixes: list[str],
) -> None:
    scoring = domain_payload.get("scoring")
    if isinstance(scoring, dict):
        pm = scoring.get("primary_metric")
        metrics = scoring.get("metrics", [])
        names = {m.get("name") for m in metrics if isinstance(m, dict)}
        if pm and pm not in names:
            issues.append(
                f"primary_metric {pm!r} is not listed in scoring.metrics (names: {names})."
            )
            fixes.append(
                "Add a MetricDef with name matching primary_metric, or change primary_metric."
            )

    vow = domain_payload.get("binding_vow", {})
    if isinstance(vow, dict):
        ep = vow.get("episode", {})
        if isinstance(ep, dict) and ep.get("max_steps") is None:
            issues.append(
                "binding_vow.episode.max_steps is unset — episodes may run unbounded in theory."
            )
            fixes.append(
                "Set episode.max_steps to your true horizon (e.g. 1 for trivia, 30-200 for games)."
            )


def validate_benchmark_config(
    domain_payload: dict[str, Any],
) -> dict[str, Any]:
    c = load_constraints()
    issues: list[str] = []
    fixes: list[str] = []
    if "error" in c:
        issues.append(c["error"])
        return {
            "ok": False,
            "issues": issues,
            "suggested_fixes": fixes,
            "rules_version": c.get("rules_version", ""),
        }

    rules_v = c.get("rules_version", "0.1.0")

    if _is_benchanything_manifest(domain_payload):
        for key in _MANIFEST_REQUIRED_KEYS:
            if key not in domain_payload or domain_payload[key] in (None, ""):
                issues.append(f"Missing or empty field: {key}")
                fixes.append(f"Set `{key}` in benchanything.json (see mesocosm init template).")
        _validate_manifest_scoring_and_vow(domain_payload, issues, fixes)
        return {
            "ok": len(issues) == 0,
            "issues": issues,
            "suggested_fixes": fixes,
            "rules_version": rules_v,
            "schema": "benchanything_manifest",
        }

    required = c.get("required_register_fields", [])
    for field in required:
        if field not in domain_payload or domain_payload[field] in (None, ""):
            issues.append(f"Missing or empty field: {field}")
            fixes.append(f"Set `{field}` in the register payload (see GET /v1/domains schema).")

    model = None
    ac = domain_payload.get("inferred_agent", {}) if "inferred_agent" in domain_payload else None
    if isinstance(ac, dict):
        model = ac.get("model")

    allowed = c.get("allowed_model_prefixes", [])
    if model is not None and allowed:
        if not any(str(model).startswith(p) for p in allowed):
            issues.append(
                f"Model {model!r} does not match any allowed_model_prefixes (hackathon mode)."
            )
            fixes.append(f"Use a model with one of these prefixes: {allowed}")

    _validate_manifest_scoring_and_vow(domain_payload, issues, fixes)

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "suggested_fixes": fixes,
        "rules_version": rules_v,
    }
