from typing import Any, Union

from app.auth.deps import get_principal, require_member
from app.auth.principal import Guest, Member
from app.auth.resolve import auth_disabled
from app.schemas import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    DomainEnvironmentListItem,
    DomainListItem,
    RunListItem,
)
from app.services.domain_environments import list_environments_for_domain_member
from app.services.domain_runs import list_gallery_runs_for_domain, list_mine_runs_for_domain
from app.services.run_list import parse_created_before, runs_to_list_items
from app.services.url_safety import assert_public_http_url
from bench_common.core.binding_vow import BindingVow
from bench_common.core.domain import Domain, EnvironmentEndpoint, VersionEntry
from bench_common.core.scoring import ScoringConfig
from bench_common.storage import database as db
from bench_common.storage.dev_sync import ensure_gallery_visible, mirror_developer_env_from_domain
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

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


def _validate_user_endpoint(endpoint: EnvironmentEndpoint) -> None:
    if auth_disabled():
        return
    if endpoint.mode == "remote":
        assert_public_http_url(endpoint.url, field="endpoint.url")


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
    _validate_user_endpoint(req.endpoint)
    payload = req.model_dump()
    if auth_disabled():
        payload.setdefault("owner_id", req.owner_id or "local")
    else:
        payload["owner_id"] = str(member.user_id)
    domain = Domain(**payload)
    await db.save_domain(domain)
    domain = await ensure_gallery_visible(domain, github_url="")
    return domain


@router.get("")
async def list_domains(
    published: bool | None = None,
    include_archived: bool = False,
    slim: bool = Query(
        True,
        description="When true (default), return id/name/tags/image only for gallery surfaces",
    ),
) -> Union[list[DomainListItem], list[Domain]]:
    if not slim:
        return await db.list_domains(
            published_only=published is True,
            include_archived=include_archived,
        )
    rows = await db.list_domains_summary(
        published_only=published is True,
        include_archived=include_archived,
    )
    return [DomainListItem(id=r.id, name=r.name, tags=r.tags, image=r.image) for r in rows]


@router.get("/{domain_id}/runs/mine", response_model=list[RunListItem])
async def list_domain_mine_runs(
    domain_id: str,
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    cursor: str | None = Query(None, description="Id of the last run from the previous page"),
    created_before: str | None = Query(None, description="ISO-8601 created_before filter"),
    principal: Guest | Member = Depends(get_principal),
) -> list[RunListItem]:
    """Caller-owned runs for one domain (alternative to merged activity feed)."""
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    runs = await list_mine_runs_for_domain(
        domain_id,
        principal,
        limit=limit,
        cursor=cursor,
        created_before=parse_created_before(created_before),
    )
    return await runs_to_list_items(runs, include_episode_summary=True)


@router.get("/{domain_id}/runs/gallery", response_model=list[RunListItem])
async def list_domain_gallery_runs(
    domain_id: str,
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
) -> list[RunListItem]:
    """Public gallery runs for one domain as RunListItem rows."""
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    runs = await list_gallery_runs_for_domain(domain_id, limit=limit)
    return await runs_to_list_items(runs, include_episode_summary=True)


@router.get("/{domain_id}/environments", response_model=list[DomainEnvironmentListItem])
async def list_domain_environments(
    domain_id: str,
    member: Member = Depends(require_member),
) -> list[DomainEnvironmentListItem]:
    """Developer environments for a domain (member auth).

    The slim ``GET /v1/domains`` gallery list does not include environments; load
    this endpoint on domain detail instead of ``GET /v1/developer/environments``.
    """
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    rows = await list_environments_for_domain_member(domain_id, member)
    return [
        DomainEnvironmentListItem(
            id=env["id"],
            name=env["name"],
            status=env["status"],
            domain_id=env.get("domain_id"),
            env_url=env.get("env_url"),
            scope=env.get("scope", "solo"),
            team_id=env.get("team_id"),
        )
        for env in rows
    ]


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
    if req.binding_vow is not None:
        _ensure_binding_vow_matches_domain(domain_id, req.binding_vow)
    if req.endpoint is not None:
        _validate_user_endpoint(req.endpoint)
    updates = req.model_dump(exclude_none=True)
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


@router.post("/{domain_id}/archive", response_model=Domain)
async def archive_domain(
    domain_id: str,
    member: Member = Depends(require_member),
) -> Domain:
    """Archive a domain and remove it from gallery surfaces (owner-only)."""
    domain = await db.get_domain(domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    await _assert_domain_owner(domain, member)
    if domain.status == "archived":
        return domain
    await db.archive_domain_gallery(domain_id)
    archived = await db.get_domain(domain_id)
    if archived is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    return archived
