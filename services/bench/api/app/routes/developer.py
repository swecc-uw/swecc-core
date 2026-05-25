from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

import httpx
import structlog
from bench_common.config import settings
from bench_common.core.binding_vow import BindingVow
from bench_common.core.domain import Domain, EnvironmentEndpoint
from bench_common.core.scoring import ScoringConfig
from bench_common.storage import database as db
from app.auth.access import assert_dev_env_access, parse_team_id
from app.auth.deps import get_optional_principal, require_member
from app.auth.principal import Member
from app.auth.resolve import auth_disabled
from app.services import teams as team_svc
from bench.models import ActorType, EnvScope
from bench_common.storage.dev_sync import ensure_gallery_visible
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
    existing = await db.get_developer_environment_by_github_repo(owner_key, github_url)
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
    }
    await db.save_developer_environment(env)
    response.status_code = 201
    asyncio.create_task(
        _onboard_environment(env_id, github_url, owner_key, req.name, req.description, scope, team_uuid)
    )
    return env


async def _handle_duplicate_submission(
    env: dict[str, Any],
    req: SubmitEnvironmentRequest,
    github_url: str,
    response: Response,
    owner_key: str,
) -> dict[str, Any]:
    """Re-submitting the same repo for the same owner updates one row instead of creating another."""
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

    if env["status"] == "ready":
        await db.save_developer_environment(env)
        response.status_code = 200
        return env

    # failed or pending — re-run onboarding on the existing row
    env["status"] = "pending"
    env["error_message"] = None
    env["domain_id"] = None
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
) -> None:
    """Background task: clone repo via sandbox, create Domain, mark ready."""

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
                f"{settings.sandbox_url}/clone",
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
        env_url = f"{settings.sandbox_url}/envs/{env_id}"

    except httpx.TransportError as exc:
        await _update("failed", error_message=f"Sandbox unreachable: {exc}")
        return
    except Exception as exc:
        await _update("failed", error_message=str(exc))
        return

    # Build Domain from manifest
    try:
        domain_id = str(uuid.uuid4())
        vow_data: dict[str, Any] = {
            **manifest["binding_vow"],
            "id": f"{domain_id}-vow",
            "domain_id": domain_id,
        }
        vow = BindingVow.model_validate(vow_data)
        scoring = ScoringConfig.model_validate(manifest["scoring"])
        domain = Domain(
            id=domain_id,
            name=manifest.get("name", name),
            owner_id=owner_id,
            binding_vow=vow,
            endpoint=EnvironmentEndpoint(
                mode="sandbox",
                url=f"{settings.sandbox_url}/envs/{env_id}",
            ),
            scoring=scoring,
            status="draft",
            detail=manifest.get("description", description),
        )
        await db.save_domain(domain)
        domain = await ensure_gallery_visible(
            domain,
            env_row_id=env_id,
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
    member: Member = Depends(require_member),
) -> list[dict[str, Any]]:
    if team_id:
        tid = parse_team_id(team_id)
        if not await team_svc.is_member(tid, member.user_id):
            raise HTTPException(status_code=403, detail="Not a member of this team")
        return await db.list_developer_environments(scope=EnvScope.TEAM, team_id=str(tid))
    if scope == EnvScope.TEAM:
        raise HTTPException(status_code=422, detail="team_id required for team scope")
    return await db.list_developer_environments(
        scope=EnvScope.SOLO,
        actor_id=str(member.user_id),
    )


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

    # Reset to pending and re-run onboarding
    env["status"] = "pending"
    env["error_message"] = None
    env["domain_id"] = None
    env["env_url"] = None
    await db.save_developer_environment(env)
    asyncio.create_task(
        _onboard_environment(
            env_id, env["github_url"], env["owner_id"], env["name"], env["description"]
        )
    )
    return env


@router.delete("/environments/{env_id}", status_code=204)
async def delete_environment(
    env_id: str,
    principal=Depends(get_optional_principal),
) -> None:
    await assert_dev_env_access(env_id, principal)
    deleted = await db.delete_developer_environment(env_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Environment '{env_id}' not found")


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
    usage: dict[str, Any] = {}
    if env.get("domain_id"):
        usage = await db.get_domain_usage_stats(env["domain_id"])
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
    if not env.get("domain_id"):
        return {
            "domain_id": None,
            "total_runs": 0,
            "total_episodes": 0,
            "avg_score": None,
            "best_score": None,
            "leaderboard_entries": 0,
        }
    return await db.get_domain_usage_stats(env["domain_id"])


@router.get("/domains/{domain_id}/usage")
async def get_domain_usage(domain_id: str) -> dict[str, Any]:
    return await db.get_domain_usage_stats(domain_id)
