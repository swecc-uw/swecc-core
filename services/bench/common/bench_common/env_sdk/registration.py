"""
Domain registration helper.

Lets an env developer register (or update) their Domain on a BenchAnything
platform instance via the REST API.

Usage:
    from bench_common.env_sdk.registration import DomainConfig, register_domain

    cfg = DomainConfig(
        id="my-env",
        name="My Environment",
        ...
    )
    register_domain(cfg, api_url="http://localhost:8000")
"""
from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from bench_common.core.binding_vow import BindingVow
from bench_common.core.domain import EnvironmentEndpoint, VersionEntry
from bench_common.core.scoring import ScoringConfig


class DomainConfig(BaseModel):
    """
    Everything needed to register a Domain.  Fill this in inside your
    adapter package's domain.py and pass it to register_domain().
    """
    id: str
    name: str
    owner_id: str
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
    api_url: str = "http://localhost:8000",
    update_if_exists: bool = True,
) -> dict[str, Any]:
    """
    Register or update a Domain on the platform.

    Args:
        config:           Domain config built from DomainConfig.
        api_url:          Base URL of the BenchAnything API server.
        update_if_exists: If True, PATCH an existing draft domain instead
                          of raising on 409.

    Returns:
        The Domain JSON returned by the API.

    Raises:
        httpx.HTTPStatusError: On unexpected API errors.
    """
    base = api_url.rstrip("/")
    payload = config.model_dump(mode="json")

    with httpx.Client(base_url=base, timeout=30.0) as client:
        r = client.post("/v1/domains", json=payload)

        if r.status_code == 409 and update_if_exists:
            # Domain already exists — try to PATCH it (only works if still draft)
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
        result = r.json()

    print(f"[register] domain '{config.id}' registered at {base}  status={result.get('status')}")
    return result


def publish_domain(domain_id: str, *, api_url: str = "http://localhost:8000") -> dict[str, Any]:
    """
    Freeze a Domain's Binding Vow and enable it for leaderboard submissions.
    Call this once you're happy with the Binding Vow definition.
    """
    base = api_url.rstrip("/")
    with httpx.Client(base_url=base, timeout=30.0) as client:
        r = client.post(f"/v1/domains/{domain_id}/publish")
        r.raise_for_status()
        result = r.json()
    print(f"[register] domain '{domain_id}' published")
    return result
