"""
Domain registration helper.

Lets an env developer register (or update) their Domain on a BenchAnything
platform instance via the REST API.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from bench_common.auth.session import get_bench_session
from bench_common.cli.urls import default_bench_api_url
from bench_common.core.binding_vow import BindingVow
from bench_common.core.domain import EnvironmentEndpoint, VersionEntry
from bench_common.core.scoring import ScoringConfig
from pydantic import BaseModel


class DomainConfig(BaseModel):
    """
    Everything needed to register a Domain.  Fill this in inside your
    adapter package's domain.py and pass it to register_domain().
    """

    id: str
    name: str
    owner_id: str = ""  # optional when using authenticated session
    binding_vow: BindingVow
    endpoint: EnvironmentEndpoint
    scoring: ScoringConfig
    tags: list[str] = []
    detail: str = ""
    pricing: str = "free"
    version_history: list[VersionEntry] = []
    image_url: str | None = None
    profile_picture_url: str | None = None
    has_gold_benchmark: bool = False


def register_domain(
    config: DomainConfig,
    *,
    api_url: str | None = None,
    update_if_exists: bool = True,
    token: str | None = None,
) -> dict[str, Any]:
    """
    Register or update a Domain on the platform (requires member auth unless
    BENCH_AUTH_DISABLED=1).
    """
    if os.environ.get("BENCH_AUTH_DISABLED", "").lower() in ("1", "true", "yes"):
        base = (api_url or default_bench_api_url()).rstrip("/")
        payload = config.model_dump(mode="json")
        if not payload.get("owner_id"):
            payload["owner_id"] = "local"
        with httpx.Client(base_url=base, timeout=30.0) as client:
            r = client.post("/v1/domains", json=payload)
            if r.status_code == 409 and update_if_exists:
                patch_payload = {
                    k: payload[k]
                    for k in (
                        "name",
                        "binding_vow",
                        "endpoint",
                        "scoring",
                        "tags",
                        "detail",
                        "pricing",
                        "version_history",
                        "image_url",
                        "profile_picture_url",
                        "has_gold_benchmark",
                    )
                    if k in payload
                }
                r = client.patch(f"/v1/domains/{config.id}", json=patch_payload)
            r.raise_for_status()
            return r.json()

    with get_bench_session(bench_url=api_url, token=token) as session:
        payload = config.model_dump(mode="json", exclude={"owner_id"})
        r = session.client.post("/v1/domains", json=payload)
        if r.status_code == 409 and update_if_exists:
            patch_payload = {
                k: payload[k]
                for k in (
                    "name",
                    "binding_vow",
                    "endpoint",
                    "scoring",
                    "tags",
                    "detail",
                    "pricing",
                    "version_history",
                    "image_url",
                    "profile_picture_url",
                    "has_gold_benchmark",
                )
                if k in payload
            }
            r = session.client.patch(f"/v1/domains/{config.id}", json=patch_payload)
        r.raise_for_status()
        result = r.json()

    print(f"[register] domain '{config.id}' registered  status={result.get('status')}")
    return result


def publish_domain(
    domain_id: str,
    *,
    api_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Publish a domain (requires member auth)."""
    if os.environ.get("BENCH_AUTH_DISABLED", "").lower() in ("1", "true", "yes"):
        base = (api_url or default_bench_api_url()).rstrip("/")
        with httpx.Client(base_url=base, timeout=30.0) as client:
            r = client.post(f"/v1/domains/{domain_id}/publish")
            r.raise_for_status()
            return r.json()

    with get_bench_session(bench_url=api_url, token=token) as session:
        r = session.client.post(f"/v1/domains/{domain_id}/publish")
        r.raise_for_status()
        result = r.json()
    print(f"[register] domain '{domain_id}' published")
    return result
