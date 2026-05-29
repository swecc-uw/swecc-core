from datetime import timedelta

from app.auth.access import assert_run_read, parse_team_id
from app.auth.deps import get_optional_principal, get_principal
from app.auth.policy import (
    assert_guest_can_create_run,
    assert_guest_rate_limit,
    assert_run_submission_cooldown,
)
from app.auth.principal import Guest, Member
from app.auth.resolve import auth_disabled
from app.services import teams as team_svc
from app.services.run_env import resolve_run_environment_id
from bench.models import ActorType
from bench.models import DeveloperEnvironment as DevEnvRow
from bench.models import EnvScope
from bench.models import Run as RunRow
from bench.models import Visibility
from bench_common.core.run import Episode, Run, RunConfig
from bench_common.export.replay import build_run_export_dict
from bench_common.orchestrator import service as orchestrator
from bench_common.storage import database as db
from bench_common.storage.trace_store import trace_store
from django.utils import timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/runs", tags=["runs"])


class CreateRunBody(RunConfig):
    team_id: str | None = None
    visibility: str | None = None
    env_id: str | None = None


def _requester_id(principal: Guest | Member) -> str:
    if isinstance(principal, Member):
        return str(principal.user_id)
    return f"guest:{principal.session_id}"


@router.get("", response_model=list[Run])
async def list_runs(
    domain_id: str | None = None,
    env_id: str | None = None,
    principal=Depends(get_optional_principal),
) -> list[Run]:
    if auth_disabled():
        return await db.list_runs(domain_id=domain_id, env_id=env_id)

    if isinstance(principal, Guest):
        return await db.list_runs(
            domain_id=domain_id,
            env_id=env_id,
            actor_type=ActorType.GUEST,
            actor_id=principal.session_id,
        )
    if isinstance(principal, Member):
        return await db.list_runs(
            domain_id=domain_id,
            env_id=env_id,
            actor_type=ActorType.MEMBER,
            actor_id=str(principal.user_id),
        )
    # Anonymous: only gallery-visible completed runs
    rows = await db.list_gallery_runs(domain_id=domain_id, limit=50)
    return [r for r, _ in rows]


@router.post("", response_model=Run, status_code=202)
async def create_run(
    config: CreateRunBody,
    principal=Depends(get_principal),
) -> Run:
    if isinstance(principal, Guest):
        await assert_guest_rate_limit(principal.session_id)
        assert_guest_can_create_run(config.domain_id)

    if not auth_disabled():
        await assert_run_submission_cooldown(_requester_id(principal))

    team_uuid = None
    if config.team_id:
        if isinstance(principal, Guest):
            raise HTTPException(status_code=403, detail="Teams require member login")
        team_uuid = parse_team_id(config.team_id)
        if not await team_svc.is_member(team_uuid, principal.user_id):
            raise HTTPException(status_code=403, detail="Not a member of this team")

    resolved_env_id = await resolve_run_environment_id(
        env_id=config.env_id,
        domain_id=config.domain_id,
        principal=principal,
        team_id=team_uuid,
    )

    run_config = RunConfig(
        **config.model_dump(exclude={"team_id", "visibility", "env_id"}),
        env_id=resolved_env_id,
    )
    req_id = "local" if auth_disabled() else _requester_id(principal)
    try:
        run = await orchestrator.create_run(run_config, requester_id=req_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    actor_type = ActorType.MEMBER if isinstance(principal, Member) else ActorType.GUEST
    actor_id = str(principal.user_id) if isinstance(principal, Member) else principal.session_id
    if isinstance(principal, Guest):
        visibility = Visibility.GALLERY_PUBLIC
        expires = timezone.now() + timedelta(days=7)
    else:
        visibility = config.visibility or Visibility.PRIVATE
        if visibility not in (Visibility.PRIVATE, Visibility.GALLERY_PUBLIC):
            visibility = Visibility.PRIVATE
        expires = None

    if resolved_env_id:
        run = run.model_copy(update={"env_id": resolved_env_id})

    await db.save_run(
        run,
        actor_type=actor_type,
        actor_id=actor_id,
        team_id=str(team_uuid) if team_uuid else None,
        env_id=resolved_env_id,
        visibility=visibility,
        expires_at=expires,
    )
    return await db.get_run(run.id) or run


@router.post("/{run_id}/cancel", response_model=Run)
async def cancel_run(
    run_id: str,
    principal=Depends(get_principal),
) -> Run:
    await assert_run_read(run_id, principal)
    run = await db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if run.status in ("completed", "failed", "cancelled"):
        return run
    try:
        return await orchestrator.cancel_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}", response_model=Run)
async def get_run(
    run_id: str,
    principal=Depends(get_optional_principal),
) -> Run:
    await assert_run_read(run_id, principal)
    run = await db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run


@router.get("/{run_id}/episodes", response_model=list[Episode])
async def list_episodes(
    run_id: str,
    principal=Depends(get_optional_principal),
) -> list[Episode]:
    await assert_run_read(run_id, principal)
    return await db.get_episodes(run_id)


@router.get("/{run_id}/traces")
async def get_traces(
    run_id: str,
    principal=Depends(get_optional_principal),
) -> dict:
    await assert_run_read(run_id, principal)
    episodes = await db.get_episodes(run_id)
    result = {}
    for ep in episodes:
        events = await trace_store.read(ep.id)
        result[ep.id] = [e.model_dump(mode="json") for e in events]
    return result


@router.get("/{run_id}/export")
async def export_run(
    run_id: str,
    principal=Depends(get_optional_principal),
) -> dict:
    """
    Full run bundle for repo-local showcase frontends.

    Includes run metadata, episodes, raw traces, and a ``replay`` map with
    per-step ``reasoning`` (model text), observations, and actions.
    Readable without auth when the run is gallery_public and completed.
    """
    row = await assert_run_read(run_id, principal)
    run = await db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    tid = str(row.team_id) if row.team_id else None
    if run.team_id != tid:
        run = run.model_copy(update={"team_id": tid})

    domain = await db.get_domain(run.config.domain_id)
    episodes = await db.get_episodes(run_id)
    traces_by_episode: dict[str, list] = {}
    for ep in episodes:
        traces_by_episode[ep.id] = await trace_store.read(ep.id)

    # Redact author + model fields when the viewer is not the owner/teammate.
    # Public-gallery surfaces are world-readable when status=completed, so any
    # anonymous viewer hitting this endpoint must not see raw chain-of-thought,
    # author system prompts, or internal user IDs.
    redact_sensitive = not await _viewer_owns_run(row, principal)

    return build_run_export_dict(
        run=run,
        episodes=episodes,
        traces_by_episode=traces_by_episode,
        visibility=row.visibility,
        domain_name=domain.name if domain else None,
        redact_sensitive=redact_sensitive,
    )


async def _viewer_owns_run(row: RunRow, principal) -> bool:
    """True when the viewer is the run's author or a teammate — i.e. allowed
    to see raw prompts, raw chain-of-thought, and internal IDs.  Public-gallery
    viewers get a redacted bundle."""
    if auth_disabled():
        return True
    if isinstance(principal, Member):
        if row.actor_type == ActorType.MEMBER and row.actor_id == str(principal.user_id):
            return True
        if row.team_id:
            return await team_svc.is_member(row.team_id, principal.user_id)
    if isinstance(principal, Guest):
        return row.actor_type == ActorType.GUEST and row.actor_id == principal.session_id
    return False
