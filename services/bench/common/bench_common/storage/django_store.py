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
from typing import Any, NamedTuple, TypeVar

from asgiref.sync import sync_to_async

# These imports require django.setup() to have been called already.
from bench.models import ActorType
from bench.models import BenchJob as BenchJobRow
from bench.models import BenchTeam as BenchTeamRow
from bench.models import DeveloperEnvironment as DeveloperEnvironmentRow
from bench.models import Domain as DomainRow
from bench.models import EnvScope
from bench.models import Episode as EpisodeRow
from bench.models import Leaderboard as LeaderboardRow
from bench.models import Run as RunRow
from bench.models import Visibility
from bench_common.core.domain import Domain
from bench_common.core.run import Episode, Run
from django.db.models import Avg, Count, FloatField, Q
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.dateparse import parse_datetime
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


def _dt_or_none(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    return parsed


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


async def list_domains(
    *,
    published_only: bool = False,
    include_archived: bool = False,
) -> list[Domain]:
    qs = DomainRow.objects.all()
    if published_only:
        qs = qs.filter(published=True)
    out: list[Domain] = []
    async for row in qs:
        domain = _model_from_row_data(Domain, row.data)
        if not include_archived and domain.status == "archived":
            continue
        out.append(domain)
    return out


class DomainListEntry(NamedTuple):
    id: str
    name: str
    tags: list[str]
    image: str | None


async def list_domains_summary(
    *,
    published_only: bool = False,
    include_archived: bool = False,
) -> list[DomainListEntry]:
    domains = await list_domains(
        published_only=published_only,
        include_archived=include_archived,
    )
    return [
        DomainListEntry(
            id=d.id,
            name=d.name,
            tags=list(d.tags),
            image=d.image_url or d.profile_picture_url,
        )
        for d in domains
    ]


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
    status_in: list[str] | None = None,
    limit: int = 100,
    cursor: str | None = None,
    created_before: datetime | None = None,
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
    if status_in:
        qs = qs.filter(status__in=status_in)
    if created_before is not None:
        qs = qs.filter(data__created_at__lt=created_before.isoformat())
    if cursor:
        try:
            cur_row = await RunRow.objects.aget(id=cursor)
            cur_created = _run_from_row(cur_row).created_at.isoformat()
            qs = qs.filter(
                Q(data__created_at__lt=cur_created)
                | (Q(data__created_at=cur_created) & Q(id__lt=cursor))
            )
        except RunRow.DoesNotExist:
            pass
    qs = qs.order_by("-data__created_at", "-id")
    return [_run_from_row(row) async for row in qs[:limit]]


class EpisodeSummary(NamedTuple):
    completed_count: int
    failed_count: int
    avg_reward: float | None


_FAILED_EPISODE_STATUSES = ("failed", "timeout", "cancelled")


async def episode_summaries_for_runs(run_ids: list[str]) -> dict[str, EpisodeSummary]:
    if not run_ids:
        return {}
    reward_key = KeyTextTransform("total_reward", "data")
    rows = (
        EpisodeRow.objects.filter(run_id__in=run_ids)
        .values("run_id")
        .annotate(
            completed_count=Count("id", filter=Q(status="completed")),
            failed_count=Count("id", filter=Q(status__in=_FAILED_EPISODE_STATUSES)),
            avg_reward=Avg(Cast(reward_key, FloatField())),
        )
    )
    out: dict[str, EpisodeSummary] = {}
    async for row in rows:
        avg = row["avg_reward"]
        out[row["run_id"]] = EpisodeSummary(
            completed_count=row["completed_count"] or 0,
            failed_count=row["failed_count"] or 0,
            avg_reward=float(avg) if avg is not None else None,
        )
    return out


async def list_active_runs(
    *,
    domain_id: str | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    limit: int = 50,
) -> list[Run]:
    return await list_runs(
        domain_id,
        actor_type=actor_type,
        actor_id=actor_id,
        status_in=["pending", "running"],
        limit=limit,
    )


class LeaderboardRun(NamedTuple):
    run: Run
    num_episodes: int


async def list_leaderboard_runs(
    domain_id: str,
    *,
    primary_metric: str,
    higher_is_better: bool,
    limit: int,
) -> list[LeaderboardRun]:
    """Completed gallery-public runs for a published domain, ordered by primary score."""
    score_path = KeyTextTransform(primary_metric, "data__scores")
    qs = (
        RunRow.objects.filter(
            domain_id=domain_id,
            visibility=Visibility.GALLERY_PUBLIC,
            status="completed",
            domain__published=True,
        )
        .exclude(data__scores__isnull=True)
        .annotate(primary_score=Cast(score_path, FloatField()))
        .filter(primary_score__isnull=False)
    )
    order = "-primary_score" if higher_is_better else "primary_score"
    out: list[LeaderboardRun] = []
    async for row in qs.order_by(order, "-id")[:limit]:
        run = _run_from_row(row)
        ep_count = await EpisodeRow.objects.filter(run_id=row.id).acount()
        out.append(LeaderboardRun(run=run, num_episodes=ep_count))
    return out


async def reap_orphan_work() -> dict[str, int]:
    """Mark in-flight rows as failed after a bench-api restart.

    `_active_run_tasks` lives in process memory, so a crash/redeploy strands
    any `running`/`pending` run, episode, or `cloning` developer env. Without
    this sweep, those rows stay non-terminal forever — `cancel_run` flips the
    flag but no worker is left to react, and the UI shows "running" indefinitely.

    UNSAFE for multi-replica deploys (would mark the OTHER replica's live work
    as failed). Gated behind `settings.enable_orphan_reaper` at the call site.
    """

    def _patch_data(
        payload: Any, *, status: str, reason: str, terminal_field: str
    ) -> dict[str, Any]:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload["status"] = status
        # Run uses `completed_at`; Episode uses `ended_at`. Picking the wrong
        # name silently drops on Pydantic round-trip and leaves UI/exports
        # showing a terminal episode with no end time.
        payload.setdefault(terminal_field, datetime.utcnow().isoformat())
        terminal_info = payload.get("terminal_info") or {}
        if isinstance(terminal_info, dict):
            terminal_info.setdefault("reason", reason)
            payload["terminal_info"] = terminal_info
        return payload

    orphan_run_qs = RunRow.objects.filter(status__in=["pending", "running"])
    orphan_runs = [row async for row in orphan_run_qs]
    run_count = 0
    for row in orphan_runs:
        row.status = "failed"
        row.data = _patch_data(
            row.data,
            status="failed",
            reason="bench_api_restart",
            terminal_field="completed_at",
        )
        await row.asave(update_fields=["status", "data"])
        run_count += 1

    orphan_ep_qs = EpisodeRow.objects.filter(status__in=["pending", "running"])
    orphan_eps = [row async for row in orphan_ep_qs]
    ep_count = 0
    for row in orphan_eps:
        row.status = "failed"
        row.data = _patch_data(
            row.data,
            status="failed",
            reason="bench_api_restart",
            terminal_field="ended_at",
        )
        await row.asave(update_fields=["status", "data"])
        ep_count += 1

    env_count = await DeveloperEnvironmentRow.objects.filter(status="cloning").aupdate(
        status="failed",
        error_message="bench-api restarted while cloning; resubmit to retry",
    )

    # BenchJob rows live in a separate table.  Once a worker claims a job and
    # then dies, the row stays "running" forever — claim_bench_job filters on
    # status="queued" so nothing can pick it up again, and there's no
    # heartbeat to detect liveness.
    bench_job_count = await BenchJobRow.objects.filter(status="running").aupdate(
        status="failed",
        completed_at=timezone.now(),
    )

    return {
        "runs": run_count,
        "episodes": ep_count,
        "developer_envs": env_count,
        "bench_jobs": bench_job_count,
    }


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
        "submission_version": env.get("submission_version", 1),
        "domain_history": env.get("domain_history") or [],
        "resubmitted_at": _dt_or_none(env.get("resubmitted_at")),
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
        if scope == EnvScope.SOLO:
            qs = qs.filter(Q(scope=scope) | Q(scope="") | Q(scope__isnull=True))
        else:
            qs = qs.filter(scope=scope)
    if team_id:
        qs = qs.filter(team_id=team_id)
    if actor_id:
        if scope == EnvScope.SOLO:
            qs = qs.filter(Q(actor_id=actor_id) | Q(actor_id__isnull=True, owner_id=actor_id))
        else:
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
        "submission_version": row.submission_version,
        "domain_history": row.domain_history or [],
        "resubmitted_at": _iso_dt(row.resubmitted_at),
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

    domain = await get_domain(domain_id)
    try:
        domain_row = await DomainRow.objects.aget(id=domain_id)
        domain_published = domain_row.published
    except DomainRow.DoesNotExist:
        domain_published = False
    primary = domain.scoring.primary_metric if domain else None

    by_status: dict[str, int] = {}
    total_episodes = 0
    gallery_eligible = 0
    leaderboard_eligible = 0
    primary_scores: list[float] = []

    for r in run_rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        run = _model_from_row_data(Run, r.data)
        total_episodes += run.config.num_episodes if run.config else 0

        is_gallery = (
            r.visibility == Visibility.GALLERY_PUBLIC
            and r.status == "completed"
            and domain_published
        )
        if is_gallery:
            gallery_eligible += 1
            if run.scores:
                leaderboard_eligible += 1
                if primary is not None:
                    primary_scores.append(run.scores.get(primary, 0.0))

    avg_score = sum(primary_scores) / len(primary_scores) if primary_scores else None
    best_score = max(primary_scores) if primary_scores else None

    return {
        "domain_id": domain_id,
        "total_runs": total_runs,
        "total_episodes": total_episodes,
        "avg_score": avg_score,
        "best_score": best_score,
        "leaderboard_entries": leaderboard_eligible,
        "by_status": by_status,
        "gallery_eligible": gallery_eligible,
        "leaderboard_eligible": leaderboard_eligible,
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
