from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from bench_common.core.domain import Domain, EnvironmentEndpoint, VersionEntry
from bench_common.core.binding_vow import BindingVow
from bench_common.core.scoring import ScoringConfig
from bench_common.storage import database as db

router = APIRouter(prefix="/v1/domains", tags=["domains"])


class CreateDomainRequest(BaseModel):
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


class UpdateDomainRequest(BaseModel):
    name: str | None = None
    binding_vow: BindingVow | None = None
    endpoint: EnvironmentEndpoint | None = None
    scoring: ScoringConfig | None = None
    tags: list[str] | None = None
    detail: str | None = None
    pricing: str | None = None
    version_history: list[VersionEntry] | None = None
    image_url: str | None = None
    profile_picture_url: str | None = None
    has_gold_benchmark: bool | None = None


@router.post("", response_model=Domain, status_code=201)
async def create_domain(req: CreateDomainRequest) -> Domain:
    existing = await db.get_domain(req.id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Domain '{req.id}' already exists")
    domain = Domain(**req.model_dump())
    await db.save_domain(domain)

    # Mirror into the developer-environments table so the SPA's /developer page
    # surfaces every Domain regardless of how it got registered (github clone,
    # direct curl, MCP register_benchmark, future SDKs). The github_url stays
    # blank for non-clone callers — the SPA card renders an "API / MCP" badge
    # instead of a GitHub link when it sees an empty string.
    existing_env = await db.get_developer_environment(domain.id)
    if existing_env is None:
        await db.save_developer_environment(
            {
                "id": domain.id,
                "owner_id": domain.owner_id,
                "name": domain.name,
                "description": domain.detail,
                "github_url": "",
                "status": "ready",
                "domain_id": domain.id,
                "env_url": domain.endpoint.url,
                "error_message": None,
                "created_at": datetime.utcnow().isoformat(),
            }
        )
    return domain


@router.get("", response_model=list[Domain])
async def list_domains(published: bool | None = None) -> list[Domain]:
    return await db.list_domains(published_only=published is True)


@router.get("/{domain_id}", response_model=Domain)
async def get_domain(domain_id: str) -> Domain:
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    return domain


@router.patch("/{domain_id}", response_model=Domain)
async def update_domain(domain_id: str, req: UpdateDomainRequest) -> Domain:
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    if domain.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Only draft domains can be updated",
        )
    updates = req.model_dump(exclude_none=True)
    updated = domain.model_copy(update=updates)
    await db.save_domain(updated)
    return updated


@router.post("/{domain_id}/publish", response_model=Domain)
async def publish_domain(domain_id: str) -> Domain:
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    updated = domain.model_copy(update={"status": "published"})
    await db.save_domain(updated)
    return updated
