"""
Load a DomainConfig from benchanything.json for local LiteLLM runs (no platform DB).
"""

from __future__ import annotations

import json
from pathlib import Path

from bench_common.core.binding_vow import BindingVow
from bench_common.core.domain import EnvironmentEndpoint
from bench_common.core.errors import ManifestError
from bench_common.core.scoring import ScoringConfig
from bench_common.env_sdk.registration import DomainConfig

_REQUIRED_KEYS = ("adapter", "name", "binding_vow", "scoring")


def load_manifest(path: str | Path) -> dict:
    """Parse and validate top-level keys in benchanything.json."""
    manifest_path = Path(path).resolve()
    if not manifest_path.exists():
        raise ManifestError(f"Manifest not found: {manifest_path}")
    try:
        manifest: dict = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"benchanything.json is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ManifestError("benchanything.json must be a JSON object")
    missing = [k for k in _REQUIRED_KEYS if k not in manifest]
    if missing:
        raise ManifestError(
            f"benchanything.json is missing required key(s): {', '.join(repr(k) for k in missing)}"
        )
    return manifest


def domain_config_from_manifest(
    path: str | Path,
    *,
    domain_id: str | None = None,
    env_url: str = "http://localhost:8765",
) -> DomainConfig:
    """
    Build a DomainConfig from benchanything.json for local benching.

    domain_id defaults to manifest ``id`` or the parent directory name.
    """
    manifest_path = Path(path).resolve()
    manifest = load_manifest(manifest_path)
    resolved_id = domain_id or manifest.get("id") or manifest_path.parent.name
    vow_version = str(manifest["binding_vow"].get("version", "1.0.0"))

    vow_raw = {
        **manifest["binding_vow"],
        "id": manifest["binding_vow"].get("id") or f"{resolved_id}-v{vow_version}",
        "domain_id": manifest["binding_vow"].get("domain_id") or resolved_id,
    }
    binding_vow = BindingVow.model_validate(vow_raw)
    binding_vow.validate()

    scoring = ScoringConfig.model_validate(manifest["scoring"])

    return DomainConfig(
        id=resolved_id,
        name=manifest["name"],
        binding_vow=binding_vow,
        endpoint=EnvironmentEndpoint(mode="remote", url=env_url.rstrip("/")),
        scoring=scoring,
        tags=manifest.get("tags") or [],
        detail=manifest.get("description") or manifest.get("detail") or "",
    )
