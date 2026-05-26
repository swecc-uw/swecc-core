"""
Django ORM storage backend.

Requires django.setup() to have been called before any function here is
invoked (bench-api does this in its main.py).  All DB credentials come from
the DB_HOST / DB_NAME / DB_USER / DB_PASSWORD / DB_PORT environment variables
read by app/django_settings.py.

Import bench_common.storage.database (re-exports this module).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, TypeVar

from asgiref.sync import sync_to_async

# These imports require django.setup() to have been called already.
from bench.models import ActorType
from bench.models import BenchTeam as BenchTeamRow
from bench.models import BenchJob as BenchJobRow
from bench.models import DeveloperEnvironment as DeveloperEnvironmentRow
from bench.models import Domain as DomainRow
from bench.models import EnvScope
from bench.models import Episode as EpisodeRow
from bench.models import Leaderboard as LeaderboardRow
from bench.models import Run as RunRow
from bench.models import Visibility
from bench_common.core.domain import Domain
from bench_common.core.run import Episode, Run
from django.utils import timezone
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def _model_from_row_data(model_cls: type[T], data: Any) -> T:
    if isinstance(data, dict):
        return model_cls.model_validate(data)
    return model_cls.model_validate_json(data)


def _iso_dt(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


from bench_common.storage.db_hints import init_db_hint


async def init_db() -> None:
    """Verify the bench tables exist; they are created by `swecc-server`'s
    `manage.py migrate` step. Fails loudly with an actionable message if not."""
    try:
        await DomainRow.objects.acount()
        await BenchTeamRow.objects.acount()
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"{init_db_hint(exc)} Original error: {exc}") from exc


# ── Domain ────────────────────────────────────────────────────────────────────


async def save_domain(domain: Domain) -> None:
    await DomainRow.objects.aupdate_or_create(
        id=domain.id,
        defaults={
            "data": domain.model_dump(mode="json"),
            "published": domain.status == "published",
        },
    )


async def get_domain(domain_id: str) -> Domain | None:
    try:
        row = await DomainRow.objects.aget(id=domain_id)
    except DomainRow.DoesNotExist:
        return None
    return _model_from_row_data(Domain, row.data)


async def list_domains(*, published_only: bool = False) -> list[Domain]:
    qs = DomainRow.objects.all()
    if published_only:
        qs = qs.filter(published=True)
    return [_model_from_row_data(Domain, row.data) async for row in qs]


# ── Run ───────────────────────────────────────────────────────────────────────


async def save_run(
    run: Run,
    *,
    actor_type: str | None = None,
    actor_id: str | None = None,
    team_id: str | None = None,
    env_id: str | None = None,
    visibility: str | None = None,
    expires_at: datetime | None = None,
) -> None:
    effective_env_id = env_id if env_id is not None else run.env_id
    if effective_env_id is not None and run.env_id != effective_env_id:
        run = run.model_copy(update={"env_id": effective_env_id})
    defaults: dict[str, Any] = {
        "data": run.model_dump(mode="json"),
        "domain_id": run.config.domain_id,
        "status": run.status,
    }
    if actor_type is not None:
        defaults["actor_type"] = actor_type
    if actor_id is not None:
        defaults["actor_id"] = actor_id
    if team_id is not None:
        defaults["team_id"] = team_id
    if visibility is not None:
        defaults["visibility"] = visibility
    if expires_at is not None:
        defaults["expires_at"] = expires_at
    await RunRow.objects.aupdate_or_create(id=run.id, defaults=defaults)


def _run_from_row(row: RunRow) -> Run:
    run = _model_from_row_data(Run, row.data)
    tid = str(row.team_id) if row.team_id else None
    if run.team_id != tid:
        return run.model_copy(update={"team_id": tid})
    return run


async def get_run(run_id: str) -> Run | None:
    try:
        row = await RunRow.objects.aget(id=run_id)
    except RunRow.DoesNotExist:
        return None
    return _run_from_row(row)


async def list_runs(
    domain_id: str | None = None,
    *,
    actor_type: str | None = None,
    actor_id: str | None = None,
    team_id: str | None = None,
    env_id: str | None = None,
    visibility: str | None = None,
    limit: int = 100,
) -> list[Run]:
    qs = RunRow.objects.all()
    if domain_id:
        qs = qs.filter(domain_id=domain_id)
    if actor_type:
        qs = qs.filter(actor_type=actor_type)
    if actor_id:
        qs = qs.filter(actor_id=actor_id)
    if team_id:
        qs = qs.filter(team_id=team_id)
    if env_id:
        qs = qs.filter(data__env_id=env_id)
    if visibility:
        qs = qs.filter(visibility=visibility)
    return [_run_from_row(row) async for row in qs.order_by("-id")[:limit]]


async def archive_domain_gallery(domain_id: str) -> None:
    """Remove a domain and its runs from public gallery surfaces."""
    domain = await get_domain(domain_id)
    if domain is not None and domain.status != "archived":
        await save_domain(domain.model_copy(update={"status": "archived"}))
    await RunRow.objects.filter(
        domain_id=domain_id,
        visibility=Visibility.GALLERY_PUBLIC,
    ).aupdate(visibility=Visibility.PRIVATE)


async def list_gallery_runs(
    *,
    domain_id: str | None = None,
    limit: int = 50,
) -> list[tuple[Run, RunRow]]:
    qs = RunRow.objects.filter(
        visibility=Visibility.GALLERY_PUBLIC,
        status="completed",
        domain__published=True,
    )
    if domain_id:
        qs = qs.filter(domain_id=domain_id)
    out: list[tuple[Run, RunRow]] = []
    async for row in qs.order_by("-id")[:limit]:
        out.append((_model_from_row_data(Run, row.data), row))
    return out


# ── Episode ───────────────────────────────────────────────────────────────────


async def save_episode(episode: Episode) -> None:
    await EpisodeRow.objects.aupdate_or_create(
        id=episode.id,
        defaults={
            "data": episode.model_dump(mode="json"),
            "run_id": episode.run_id,
            "status": episode.status,
        },
    )


async def get_episode(episode_id: str) -> Episode | None:
    try:
        row = await EpisodeRow.objects.aget(id=episode_id)
    except EpisodeRow.DoesNotExist:
        return None
    return _model_from_row_data(Episode, row.data)


async def get_episodes(run_id: str) -> list[Episode]:
    return [
        _model_from_row_data(Episode, row.data)
        async for row in EpisodeRow.objects.filter(run_id=run_id)
    ]


# ── Developer Environments ────────────────────────────────────────────────────


async def save_developer_environment(env: dict[str, Any]) -> None:
    defaults: dict[str, Any] = {
        "owner_id": env["owner_id"],
        "name": env["name"],
        "description": env.get("description", ""),
        "github_url": env["github_url"],
        "status": env.get("status", "pending"),
        "domain_id": env.get("domain_id"),
        "env_url": env.get("env_url"),
        "error_message": env.get("error_message"),
        "scope": env.get("scope", EnvScope.SOLO),
        "actor_type": env.get("actor_type"),
        "actor_id": env.get("actor_id"),
        "created_by_user_id": env.get("created_by_user_id"),
        "team_id": env.get("team_id"),
    }
    await DeveloperEnvironmentRow.objects.aupdate_or_create(id=env["id"], defaults=defaults)


async def get_developer_environment(env_id: str) -> dict[str, Any] | None:
    try:
        row = await DeveloperEnvironmentRow.objects.aget(id=env_id)
    except DeveloperEnvironmentRow.DoesNotExist:
        return None
    return _dev_env_to_dict(row)


async def get_developer_environment_by_github_repo(
    owner_id: str,
    github_url: str,
) -> dict[str, Any] | None:
    """Return the newest developer env for this owner + repo URL (normalized)."""
    from bench_common.utils.github import normalize_github_url

    target = normalize_github_url(github_url)
    qs = DeveloperEnvironmentRow.objects.filter(owner_id=owner_id).order_by("-created_at")
    async for row in qs:
        if normalize_github_url(row.github_url) == target:
            return _dev_env_to_dict(row)
    return None


async def delete_developer_environment(env_id: str) -> bool:
    deleted, _ = await DeveloperEnvironmentRow.objects.filter(id=env_id).adelete()
    return deleted > 0


async def list_developer_environments(
    *,
    owner_id: str | None = None,
    scope: str | None = None,
    team_id: str | None = None,
    actor_id: str | None = None,
    domain_id: str | None = None,
) -> list[dict[str, Any]]:
    qs = DeveloperEnvironmentRow.objects.all().order_by("-created_at")
    if owner_id:
        qs = qs.filter(owner_id=owner_id)
    if scope:
        qs = qs.filter(scope=scope)
    if team_id:
        qs = qs.filter(team_id=team_id)
    if actor_id:
        qs = qs.filter(actor_id=actor_id)
    if domain_id:
        qs = qs.filter(domain_id=domain_id)
    return [_dev_env_to_dict(row) async for row in qs]


async def count_dev_envs(*, actor_id: str, scope: str) -> int:
    return await DeveloperEnvironmentRow.objects.filter(actor_id=actor_id, scope=scope).acount()


def _dev_env_to_dict(row: DeveloperEnvironmentRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "owner_id": row.owner_id,
        "name": row.name,
        "description": row.description,
        "github_url": row.github_url,
        "status": row.status,
        "domain_id": row.domain_id,
        "env_url": row.env_url,
        "error_message": row.error_message,
        "created_at": _iso_dt(row.created_at),
        "scope": row.scope,
        "team_id": str(row.team_id) if row.team_id else None,
        "actor_type": row.actor_type,
        "actor_id": row.actor_id,
    }


# ── Environment Usage ─────────────────────────────────────────────────────────


async def get_environment_usage_stats(env_id: str) -> dict[str, Any]:
    """Usage for runs attributed to one developer environment."""
    run_rows = [row async for row in RunRow.objects.filter(data__env_id=env_id)]
    total_runs = len(run_rows)
    domain_id = run_rows[0].domain_id if run_rows else None
    if domain_id is None:
        env_row = await DeveloperEnvironmentRow.objects.filter(id=env_id).afirst()
        domain_id = env_row.domain_id if env_row else None

    total_episodes = 0
    for r in run_rows:
        run = _model_from_row_data(Run, r.data)
        total_episodes += run.config.num_episodes if run.config else 0

    lb_rows = []
    if domain_id:
        lb_rows = [row async for row in LeaderboardRow.objects.filter(domain_id=domain_id)]
    scores = [row.primary_score for row in lb_rows]
    avg_score = sum(scores) / len(scores) if scores else None
    best_score = max(scores) if scores else None

    return {
        "domain_id": domain_id,
        "env_id": env_id,
        "total_runs": total_runs,
        "total_episodes": total_episodes,
        "avg_score": avg_score,
        "best_score": best_score,
        "leaderboard_entries": len(lb_rows),
    }


async def get_domain_usage_stats(domain_id: str) -> dict[str, Any]:
    run_rows = [row async for row in RunRow.objects.filter(domain_id=domain_id)]
    total_runs = len(run_rows)

    total_episodes = 0
    for r in run_rows:
        run = _model_from_row_data(Run, r.data)
        total_episodes += run.config.num_episodes if run.config else 0

    lb_rows = [row async for row in LeaderboardRow.objects.filter(domain_id=domain_id)]
    scores = [row.primary_score for row in lb_rows]
    avg_score = sum(scores) / len(scores) if scores else None
    best_score = max(scores) if scores else None

    return {
        "domain_id": domain_id,
        "total_runs": total_runs,
        "total_episodes": total_episodes,
        "avg_score": avg_score,
        "best_score": best_score,
        "leaderboard_entries": len(lb_rows),
    }


# ── Bench Jobs ────────────────────────────────────────────────────────────────


async def create_bench_job(env_id: str, domain_id: str | None, github_url: str) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    row = await BenchJobRow.objects.acreate(
        id=job_id,
        environment_id=env_id,
        domain_id=domain_id,
        github_url=github_url,
        status="queued",
    )
    return _bench_job_to_dict(row)


async def get_bench_job(job_id: str) -> dict[str, Any] | None:
    try:
        row = await BenchJobRow.objects.aget(id=job_id)
    except BenchJobRow.DoesNotExist:
        return None
    return _bench_job_to_dict(row)


async def list_bench_jobs(
    env_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    qs = BenchJobRow.objects.all().order_by("-created_at")
    if env_id:
        qs = qs.filter(environment_id=env_id)
    if status:
        qs = qs.filter(status=status)
    return [_bench_job_to_dict(row) async for row in qs]


async def claim_bench_job(job_id: str) -> dict[str, Any] | None:
    @sync_to_async
    def _claim() -> BenchJobRow | None:
        from django.db import transaction

        with transaction.atomic():
            row = (
                BenchJobRow.objects.select_for_update(skip_locked=True)
                .filter(id=job_id, status="queued")
                .first()
            )
            if row is None:
                return None
            row.status = "running"
            row.claimed_at = timezone.now()
            row.save(update_fields=["status", "claimed_at"])
            return row

    row = await _claim()
    return _bench_job_to_dict(row) if row else None


async def complete_bench_job(
    job_id: str, model_results: dict[str, Any], failed: bool = False
) -> dict[str, Any] | None:
    try:
        row = await BenchJobRow.objects.aget(id=job_id)
    except BenchJobRow.DoesNotExist:
        return None
    row.status = "failed" if failed else "completed"
    row.model_results = model_results
    row.completed_at = timezone.now()
    await row.asave(update_fields=["status", "model_results", "completed_at"])
    return _bench_job_to_dict(row)


def _bench_job_to_dict(row: BenchJobRow) -> dict[str, Any]:
    results = row.model_results
    if isinstance(results, str):
        results = json.loads(results) if results else None
    return {
        "id": row.id,
        "env_id": row.environment_id,
        "domain_id": row.domain_id,
        "github_url": row.github_url,
        "status": row.status,
        "model_results": results,
        "claimed_at": _iso_dt(row.claimed_at),
        "completed_at": _iso_dt(row.completed_at),
        "created_at": _iso_dt(row.created_at),
    }
