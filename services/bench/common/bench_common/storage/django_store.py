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
from bench_common.core.domain import Domain
from bench_common.core.run import Episode, Run
from django.utils import timezone
from pydantic import BaseModel

# These imports require django.setup() to have been called already.
from bench.models import BenchJob as BenchJobRow
from bench.models import DeveloperEnvironment as DeveloperEnvironmentRow
from bench.models import Domain as DomainRow
from bench.models import Episode as EpisodeRow
from bench.models import Leaderboard as LeaderboardRow
from bench.models import Run as RunRow

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


async def init_db() -> None:
    """Verify the bench tables exist; they are created by `swecc-server`'s
    `manage.py migrate` step. Fails loudly with an actionable message if not."""
    try:
        await DomainRow.objects.acount()
    except Exception as exc:  # pragma: no cover - defensive
        hint = (
            "bench tables missing — run swecc-server `manage.py migrate` first, "
            "then restart bench-api."
        )
        err = str(exc).lower()
        if "tenant or user not found" in err or "password authentication failed" in err:
            hint = (
                "Postgres auth failed for bench-api. On Swarm, bench-api uses Docker "
                "config server_env (same as server) — fix DB_* there and redeploy."
            )
        elif "connection" in err or "operationalerror" in type(exc).__name__.lower():
            hint = (
                "Postgres unreachable from bench-api. Check DB_HOST/DB_PORT/DB_USER "
                "(Supabase pooler :6543 needs user postgres.<project-ref>)."
            )
        raise RuntimeError(f"{hint} Original error: {exc}") from exc


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


async def save_run(run: Run) -> None:
    await RunRow.objects.aupdate_or_create(
        id=run.id,
        defaults={
            "data": run.model_dump(mode="json"),
            "domain_id": run.config.domain_id,
            "status": run.status,
        },
    )


async def get_run(run_id: str) -> Run | None:
    try:
        row = await RunRow.objects.aget(id=run_id)
    except RunRow.DoesNotExist:
        return None
    return _model_from_row_data(Run, row.data)


async def list_runs(domain_id: str | None = None) -> list[Run]:
    qs = RunRow.objects.all()
    if domain_id:
        qs = qs.filter(domain_id=domain_id)
    return [_model_from_row_data(Run, row.data) async for row in qs]


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
    await DeveloperEnvironmentRow.objects.aupdate_or_create(
        id=env["id"],
        defaults={
            "owner_id": env["owner_id"],
            "name": env["name"],
            "description": env.get("description", ""),
            "github_url": env["github_url"],
            "status": env.get("status", "pending"),
            "domain_id": env.get("domain_id"),
            "env_url": env.get("env_url"),
            "error_message": env.get("error_message"),
        },
    )


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
    qs = DeveloperEnvironmentRow.objects.filter(owner_id=owner_id).order_by(
        "-created_at"
    )
    async for row in qs:
        if normalize_github_url(row.github_url) == target:
            return _dev_env_to_dict(row)
    return None


async def delete_developer_environment(env_id: str) -> bool:
    deleted, _ = await DeveloperEnvironmentRow.objects.filter(id=env_id).adelete()
    return deleted > 0


async def list_developer_environments(
    owner_id: str | None = None,
) -> list[dict[str, Any]]:
    qs = DeveloperEnvironmentRow.objects.all().order_by("-created_at")
    if owner_id:
        qs = qs.filter(owner_id=owner_id)
    return [_dev_env_to_dict(row) async for row in qs]


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
    }


# ── Environment Usage ─────────────────────────────────────────────────────────


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


async def create_bench_job(
    env_id: str, domain_id: str | None, github_url: str
) -> dict[str, Any]:
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
