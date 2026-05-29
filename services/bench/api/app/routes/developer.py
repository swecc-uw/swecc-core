from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

import httpx
import structlog
from app.auth.access import assert_dev_env_access, parse_team_id
from app.auth.deps import get_optional_principal, require_member
from app.auth.principal import Member
from app.auth.resolve import auth_disabled
from app.schemas import RunListItem
from app.services import teams as team_svc
from bench.models import ActorType, EnvScope
from bench_common.config import settings
from bench_common.core.binding_vow import BindingVow
from bench_common.core.domain import Domain, EnvironmentEndpoint, VersionEntry
from bench_common.core.scoring import ScoringConfig
from bench_common.storage import database as db
from bench_common.storage.dev_sync import ensure_gallery_visible, mirror_developer_env_from_domain
from bench_common.utils.github import normalize_github_url
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

log = structlog.get_logger()
router = APIRouter(prefix="/v1/developer", tags=["developer"])


class SubmitEnvironmentRequest(BaseModel):
    name: str
    description: str = ""
    github_url: str
    team_id: str | None = None
    owner_id: str | None = None  # ignored when auth enabled


class DeveloperEnvironment(BaseModel):
    id: str
    owner_id: str
    name: str
    description: str
    github_url: str
    status: str
    domain_id: str | None
    env_url: str | None
    error_message: str | None
    created_at: str
    scope: str = EnvScope.SOLO
    team_id: str | None = None
    submission_version: int = 1
    domain_history: list[dict[str, Any]] = []
    resubmitted_at: str | None = None


class EnvironmentWithUsage(DeveloperEnvironment):
    usage: dict[str, Any]


class EnvPollResponse(BaseModel):
    id: str
    status: str
    domain_id: str | None
    env_url: str | None
    error_message: str | None


@router.post("/environments", response_model=DeveloperEnvironment)
async def submit_environment(
    req: SubmitEnvironmentRequest,
    response: Response,
    member: Member = Depends(require_member),
) -> dict[str, Any]:
    github_url = normalize_github_url(req.github_url)
    owner_key = str(member.user_id) if not auth_disabled() else (req.owner_id or "local")
    team_uuid = parse_team_id(req.team_id) if req.team_id else None
    if team_uuid and not await team_svc.is_member(team_uuid, member.user_id):
        raise HTTPException(status_code=403, detail="Not a member of this team")

    scope = EnvScope.TEAM if team_uuid else EnvScope.SOLO
    existing = await _find_existing_submission(scope, owner_key, github_url, team_uuid)
    if existing is not None:
        return await _handle_duplicate_submission(existing, req, github_url, response, owner_key)

    env_id = str(uuid.uuid4())
    env: dict[str, Any] = {
        "id": env_id,
        "owner_id": owner_key,
        "name": req.name,
        "description": req.description,
        "github_url": github_url,
        "status": "pending",
        "domain_id": None,
        "env_url": None,
        "error_message": None,
        "created_at": datetime.utcnow().isoformat(),
        "scope": scope,
        "actor_type": ActorType.MEMBER,
        "actor_id": owner_key,
        "created_by_user_id": member.user_id,
        "team_id": str(team_uuid) if team_uuid else None,
        "submission_version": 1,
        "domain_history": [],
        "resubmitted_at": None,
    }
    await db.save_developer_environment(env)
    response.status_code = 201
    asyncio.create_task(
        _onboard_environment(
            env_id, github_url, owner_key, req.name, req.description, scope, team_uuid
        )
    )
    return env


async def _find_existing_submission(
    scope: str,
    owner_key: str,
    github_url: str,
    team_id: uuid.UUID | None,
) -> dict[str, Any] | None:
    if scope == EnvScope.TEAM and team_id is not None:
        target = normalize_github_url(github_url)
        envs = await db.list_developer_environments(
            scope=EnvScope.TEAM,
            team_id=str(team_id),
        )
        for env in envs:
            if normalize_github_url(env["github_url"]) == target:
                return env
        return None
    return await db.get_developer_environment_by_github_repo(owner_key, github_url)


async def _domain_from_manifest(
    *,
    manifest: dict[str, Any],
    owner_id: str,
    env_id: str,
    sandbox_base: str,
    name: str,
    description: str,
    reuse_domain_id: str | None,
) -> Domain:
    """Create a new domain or update an existing one in place (resubmit / retry)."""
    existing = await db.get_domain(reuse_domain_id) if reuse_domain_id else None
    if reuse_domain_id:
        domain_id = reuse_domain_id
        prior_status = existing.status if existing else "draft"
        version_history = list(existing.version_history) if existing else []
    else:
        domain_id = str(uuid.uuid4())
        prior_status = "draft"
        version_history = []

    vow_data: dict[str, Any] = {
        **manifest["binding_vow"],
        "id": f"{domain_id}-vow",
        "domain_id": domain_id,
    }
    vow = BindingVow.model_validate(vow_data)
    scoring = ScoringConfig.model_validate(manifest["scoring"])

    if existing and vow.version != existing.binding_vow.version:
        version_history.append(
            VersionEntry(
                version=vow.version,
                date=datetime.utcnow().strftime("%Y-%m-%d"),
                changes="Environment resubmitted from GitHub",
            )
        )

    base = {
        "id": domain_id,
        "name": manifest.get("name", name),
        "owner_id": owner_id,
        "binding_vow": vow,
        "endpoint": EnvironmentEndpoint(
            mode="sandbox",
            url=f"{sandbox_base}/envs/{env_id}",
        ),
        "scoring": scoring,
        "status": prior_status,
        "detail": manifest.get("description", description),
        "version_history": version_history,
    }
    if existing:
        return existing.model_copy(
            update={
                **base,
                "tags": existing.tags,
                "pricing": existing.pricing,
                "image_url": existing.image_url,
                "profile_picture_url": existing.profile_picture_url,
                "has_gold_benchmark": existing.has_gold_benchmark,
            }
        )
    return Domain(**base)


async def _persist_domain_after_onboard(
    domain: Domain,
    *,
    env_id: str,
    github_url: str,
) -> Domain:
    await db.save_domain(domain)
    if domain.status == "published":
        await mirror_developer_env_from_domain(
            domain,
            env_row_id=env_id,
            github_url=github_url,
        )
        return domain
    return await ensure_gallery_visible(
        domain,
        env_row_id=env_id,
        github_url=github_url,
    )


async def _handle_duplicate_submission(
    env: dict[str, Any],
    req: SubmitEnvironmentRequest,
    github_url: str,
    response: Response,
    owner_key: str,
) -> dict[str, Any]:
    """Update one existing env row for a duplicate repo submission."""
    if env["status"] == "cloning":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This repository is already being onboarded",
                "environment_id": env["id"],
            },
        )

    env["name"] = req.name
    env["description"] = req.description
    env["github_url"] = github_url

    reuse_domain_id = env.get("domain_id")
    env["submission_version"] = int(env.get("submission_version") or 1) + 1
    env["resubmitted_at"] = datetime.utcnow().isoformat()
    env["status"] = "pending"
    env["error_message"] = None
    env["env_url"] = None
    await db.save_developer_environment(env)
    response.status_code = 200
    asyncio.create_task(
        _onboard_environment(
            env["id"],
            github_url,
            owner_key,
            env["name"],
            env["description"],
            env.get("scope", EnvScope.SOLO),
            uuid.UUID(env["team_id"]) if env.get("team_id") else None,
            reuse_domain_id=reuse_domain_id,
        )
    )
    return env


async def _onboard_environment(
    env_id: str,
    github_url: str,
    owner_id: str,
    name: str,
    description: str,
    scope: str = EnvScope.SOLO,
    team_id: uuid.UUID | None = None,
    *,
    reuse_domain_id: str | None = None,
) -> None:
    """Background task: clone repo via sandbox, create or update Domain, mark ready."""
    sandbox_base = settings.sandbox_url.rstrip("/")

    async def _update(status: str, **kwargs: Any) -> None:
        env = await db.get_developer_environment(env_id)
        if env is None:
            return
        env["status"] = status
        env.update(kwargs)
        await db.save_developer_environment(env)

    await _update("cloning")
    log.info("onboarding_started", env_id=env_id, github_url=github_url)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{sandbox_base}/clone",
                json={"env_id": env_id, "github_url": github_url},
            )
        if resp.status_code != 200:
            detail = resp.json().get("detail", resp.text)
            await _update("failed", error_message=detail)
            return

        payload = resp.json()
        manifest: dict[str, Any] = payload["manifest"]
        # Use the sandbox reverse-proxy path, not payload["url"] (direct subprocess
        # port on localhost inside the sandbox container — unreachable from bench-api).
        env_url = f"{sandbox_base}/envs/{env_id}"

    except httpx.TransportError as exc:
        await _update("failed", error_message=f"Sandbox unreachable: {exc}")
        return
    except Exception as exc:
        await _update("failed", error_message=str(exc))
        return

    # Build or update Domain from manifest (resubmit keeps the same domain_id)
    try:
        domain = await _domain_from_manifest(
            manifest=manifest,
            owner_id=owner_id,
            env_id=env_id,
            sandbox_base=sandbox_base,
            name=name,
            description=description,
            reuse_domain_id=reuse_domain_id,
        )
        domain = await _persist_domain_after_onboard(
            domain,
            env_id=env_id,
            github_url=github_url,
        )
    except Exception as exc:
        log.exception("domain_creation_failed", env_id=env_id)
        await _update("failed", error_message=f"Domain creation failed: {exc}")
        return

    await _update(
        "ready",
        domain_id=domain.id,
        env_url=env_url,
        error_message=None,
    )
    log.info("onboarding_complete", env_id=env_id, domain_id=domain.id)


@router.get("/environments", response_model=list[DeveloperEnvironment])
async def list_environments(
    scope: str | None = Query(None),
    team_id: str | None = Query(None),
    domain_id: str | None = Query(None),
    member: Member = Depends(require_member),
) -> list[dict[str, Any]]:
    if domain_id and not scope and not team_id:
        solo = await db.list_developer_environments(
            scope=EnvScope.SOLO,
            actor_id=str(member.user_id),
            domain_id=domain_id,
        )
        teams = await team_svc.list_teams_for_user(member.user_id)
        team_envs: list[dict[str, Any]] = []
        for t in teams:
            tid = parse_team_id(t["team_id"])
            if tid:
                team_envs.extend(
                    await db.list_developer_environments(
                        scope=EnvScope.TEAM,
                        team_id=str(tid),
                        domain_id=domain_id,
                    )
                )
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for env in solo + team_envs:
            eid = env.get("id")
            if eid and eid not in seen:
                seen.add(eid)
                out.append(env)
        return out

    if team_id:
        tid = parse_team_id(team_id)
        if not await team_svc.is_member(tid, member.user_id):
            raise HTTPException(status_code=403, detail="Not a member of this team")
        return await db.list_developer_environments(
            scope=EnvScope.TEAM,
            team_id=str(tid),
            domain_id=domain_id,
        )
    if scope == EnvScope.TEAM:
        raise HTTPException(status_code=422, detail="team_id required for team scope")
    return await db.list_developer_environments(
        scope=EnvScope.SOLO,
        actor_id=str(member.user_id),
        domain_id=domain_id,
    )


@router.get("/environments/{env_id}/runs")
async def list_environment_runs(
    env_id: str,
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="Recent runs for this environment (default 10, max 50)",
    ),
    member: Member = Depends(require_member),
) -> list[RunListItem]:
    from app.services.run_list import runs_to_list_items

    await assert_dev_env_access(env_id, member)
    runs = await db.list_runs(env_id=env_id, limit=limit)
    return await runs_to_list_items(runs, include_episode_summary=True)


@router.post("/environments/{env_id}/retry", response_model=DeveloperEnvironment)
async def retry_environment(
    env_id: str,
    principal=Depends(get_optional_principal),
) -> dict[str, Any]:
    """Re-trigger cloning for a failed or pending environment after the repo has been fixed."""
    await assert_dev_env_access(env_id, principal)
    env = await db.get_developer_environment(env_id)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{env_id}' not found")
    if env["status"] == "cloning":
        raise HTTPException(status_code=409, detail="Environment is already cloning")
    if env["status"] == "ready":
        raise HTTPException(status_code=409, detail="Environment is already ready")

    # Reset to pending and re-run onboarding (reuse domain_id when already assigned)
    reuse_domain_id = env.get("domain_id")
    env["status"] = "pending"
    env["error_message"] = None
    env["env_url"] = None
    await db.save_developer_environment(env)
    asyncio.create_task(
        _onboard_environment(
            env_id,
            env["github_url"],
            env["owner_id"],
            env["name"],
            env["description"],
            env.get("scope", EnvScope.SOLO),
            uuid.UUID(env["team_id"]) if env.get("team_id") else None,
            reuse_domain_id=reuse_domain_id,
        )
    )
    return env


@router.delete("/environments/{env_id}", status_code=204)
async def delete_environment(
    env_id: str,
    principal=Depends(get_optional_principal),
) -> None:
    await assert_dev_env_access(env_id, principal)
    env = await db.get_developer_environment(env_id)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{env_id}' not found")
    domain_id = env.get("domain_id")
    deleted = await db.delete_developer_environment(env_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Environment '{env_id}' not found")
    if domain_id:
        await db.archive_domain_gallery(domain_id)


@router.get("/environments/{env_id}/poll", response_model=EnvPollResponse)
async def poll_environment(
    env_id: str,
    principal=Depends(get_optional_principal),
) -> dict[str, Any]:
    await assert_dev_env_access(env_id, principal)
    env = await db.get_developer_environment(env_id)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{env_id}' not found")
    return {
        "id": env["id"],
        "status": env["status"],
        "domain_id": env.get("domain_id"),
        "env_url": env.get("env_url"),
        "error_message": env.get("error_message"),
    }


@router.get("/environments/{env_id}", response_model=EnvironmentWithUsage)
async def get_environment(
    env_id: str,
    principal=Depends(get_optional_principal),
) -> dict[str, Any]:
    await assert_dev_env_access(env_id, principal)
    env = await db.get_developer_environment(env_id)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{env_id}' not found")
    usage = await db.get_environment_usage_stats(env_id)
    return {**env, "usage": usage}


@router.get("/environments/{env_id}/usage")
async def get_environment_usage(
    env_id: str,
    principal=Depends(get_optional_principal),
) -> dict[str, Any]:
    await assert_dev_env_access(env_id, principal)
    env = await db.get_developer_environment(env_id)
    if env is None:
        raise HTTPException(status_code=404, detail=f"Environment '{env_id}' not found")
    return await db.get_environment_usage_stats(env_id)


@router.get("/domains/{domain_id}/usage")
async def get_domain_usage(domain_id: str) -> dict[str, Any]:
    return await db.get_domain_usage_stats(domain_id)
