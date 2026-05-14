from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def sha256_digest(obj: Any) -> str:
    h = hashlib.sha256(_canonical_json(obj)).hexdigest()
    return f"sha256:{h}"


def compile_benchmark_artifacts(domain: dict[str, Any]) -> dict[str, Any]:
    """
    Synthesize stable artifact views from a Domain object returned by the API.
    """
    contract = domain.get("binding_vow")
    eval_profile: dict[str, Any] = {
        "scoring": domain.get("scoring"),
        "domain_id": domain.get("id"),
        "status": domain.get("status"),
    }
    dataset_lock: dict[str, Any] = {
        "note": "No dataset lock is stored on the server yet. Pin seeds and env version in your repo.",
        "domain_id": domain.get("id"),
    }
    return {
        "contract.json": contract,
        "eval_profile.json": eval_profile,
        "dataset.lock.json": dataset_lock,
    }
