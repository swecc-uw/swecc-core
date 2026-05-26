from typing import Any

from bench_common.core.binding_vow import BindingVow
from bench_common.core.domain import Domain, EnvironmentEndpoint, VersionEntry
from bench_common.core.scoring import ScoringConfig
from bench_common.storage import database as db
from bench_common.storage.dev_sync import (ensure_gallery_visible,
                                           mirror_developer_env_from_domain)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.deps import require_member
from app.auth.principal import Member
from app.auth.resolve import auth_disabled

router = APIRouter(prefix="/v1/domains", tags=["domains"])


class CreateDomainRequest(BaseModel):
    id: str
    name: str
    owner_id: str | None = None  # ignored when auth enabled; derived from member
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


def _ensure_binding_vow_matches_domain(domain_id: str, vow: BindingVow) -> None:
    if vow.domain_id != domain_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"binding_vow.domain_id must match domain id: "
                f"got {vow.domain_id!r}, expected {domain_id!r}"
            ),
        )


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
async def create_domain(
    req: CreateDomainRequest,
    member: Member = Depends(require_member),
) -> Domain:
    existing = await db.get_domain(req.id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Domain '{req.id}' already exists")
    _ensure_binding_vow_matches_domain(req.id, req.binding_vow)
    payload = req.model_dump()
    if auth_disabled():
        payload.setdefault("owner_id", req.owner_id or "local")
    else:
        payload["owner_id"] = str(member.user_id)
    domain = Domain(**payload)
    await db.save_domain(domain)
    domain = await ensure_gallery_visible(domain, github_url="")
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


async def _assert_domain_owner(domain: Domain, member: Member) -> None:
    if auth_disabled():
        return
    if domain.owner_id != str(member.user_id):
        raise HTTPException(status_code=403, detail="Not allowed to modify this domain")


@router.patch("/{domain_id}", response_model=Domain)
async def update_domain(
    domain_id: str,
    req: UpdateDomainRequest,
    member: Member = Depends(require_member),
) -> Domain:
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    await _assert_domain_owner(domain, member)
    if domain.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Only draft domains can be updated",
        )
    updates = req.model_dump(exclude_none=True)
    if "binding_vow" in updates:
        _ensure_binding_vow_matches_domain(domain_id, updates["binding_vow"])
    updated = domain.model_copy(update=updates)
    await db.save_domain(updated)
    return await ensure_gallery_visible(updated)


@router.post("/{domain_id}/publish", response_model=Domain)
async def publish_domain(
    domain_id: str,
    member: Member = Depends(require_member),
) -> Domain:
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    await _assert_domain_owner(domain, member)
    updated = domain.model_copy(update={"status": "published"})
    await db.save_domain(updated)
    await mirror_developer_env_from_domain(updated)
    return updated


@router.post("/{domain_id}/unpublish", response_model=Domain)
async def unpublish_domain(
    domain_id: str,
    member: Member = Depends(require_member),
) -> Domain:
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    await _assert_domain_owner(domain, member)
    if domain.status != "published":
        raise HTTPException(
            status_code=409,
            detail="Only published domains can be unpublished",
        )
    updated = domain.model_copy(update={"status": "draft"})
    await db.save_domain(updated)
    return updated
