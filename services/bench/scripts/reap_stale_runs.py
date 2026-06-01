#!/usr/bin/env python3
"""
One-off ops script: mark stale pending/running bench rows as failed.

Mirrors POST /v1/admin/reap-stale and db.reap_stale_work() — useful when you
want to fail *all* in-flight stale rows in one shot (the background watchdog
rescues in batches of 50 and only fails after ~30m).

Usage (local, from repo root with .env loaded):
    set -a && source .env && set +a
    python services/bench/scripts/reap_stale_runs.py --dry-run
    python services/bench/scripts/reap_stale_runs.py --stale-after-seconds 0 --yes

Usage (prod bench-api container — pipe script in; image has deps + bench app):
    docker exec -i "$(docker ps -qf name=bench-api | head -1)" python - \\
        --stale-after-seconds 0 --yes \\
        < services/bench/scripts/reap_stale_runs.py

``--stale-after-seconds 0`` fails every pending/running run (and related rows).
Use a positive value to only fail rows older than that many seconds.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _bootstrap_paths() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    services_dir = repo_root / "services"
    if not services_dir.is_dir():
        # bench-api image: deps on PYTHONPATH, script may live under /tmp.
        return
    api_dir = services_dir / "bench" / "api"
    server_dir = services_dir / "server" / "server"
    common_dir = services_dir / "bench" / "common"
    # Insert in reverse order so common_dir ends up first on sys.path.
    for path in (str(api_dir), str(server_dir), str(common_dir)):
        if path not in sys.path:
            sys.path.insert(0, path)


def _parse_created_at(raw: object) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        created = raw
    elif isinstance(raw, str):
        from django.utils.dateparse import parse_datetime

        created = parse_datetime(raw)
        if created is None:
            return None
    else:
        return None
    if created.tzinfo is not None:
        return created.replace(tzinfo=None)
    return created


def _row_created_at(data: object) -> datetime | None:
    if not isinstance(data, dict):
        return None
    return _parse_created_at(data.get("created_at"))


def _is_stale(*, created_at: datetime | None, stale_after_seconds: int, now: datetime) -> bool:
    if stale_after_seconds <= 0:
        return True
    if created_at is None:
        return True
    return created_at < now - timedelta(seconds=stale_after_seconds)


def _bootstrap_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.django_settings")
    import django
    from django.apps import apps as django_apps

    if not django_apps.ready:
        django.setup()


async def _preview_stale(*, stale_after_seconds: int) -> dict[str, list[str]]:
    from bench.models import BenchJob as BenchJobRow
    from bench.models import DeveloperEnvironment as DevEnvRow
    from bench.models import Episode as EpisodeRow
    from bench.models import Run as RunRow

    now = datetime.utcnow()
    stale_run_ids: list[str] = []
    async for row in RunRow.objects.filter(status__in=["pending", "running"]).order_by("id"):
        if _is_stale(
            created_at=_row_created_at(row.data),
            stale_after_seconds=stale_after_seconds,
            now=now,
        ):
            stale_run_ids.append(row.id)

    stale_episode_ids: list[str] = []
    async for row in EpisodeRow.objects.filter(status__in=["pending", "running"]).order_by("id"):
        if stale_after_seconds > 0 and row.run_id not in stale_run_ids:
            parent = await RunRow.objects.filter(id=row.run_id).afirst()
            if parent is not None and parent.status in ("pending", "running"):
                if not _is_stale(
                    created_at=_row_created_at(parent.data),
                    stale_after_seconds=stale_after_seconds,
                    now=now,
                ):
                    continue
        stale_episode_ids.append(row.id)

    stale_env_ids: list[str] = []
    if stale_after_seconds <= 0:
        async for row in DevEnvRow.objects.filter(status="cloning").order_by("id"):
            stale_env_ids.append(row.id)

    stale_job_ids: list[str] = []
    if stale_after_seconds <= 0:
        async for row in BenchJobRow.objects.filter(status="running").order_by("id"):
            stale_job_ids.append(row.id)

    return {
        "runs": stale_run_ids,
        "episodes": stale_episode_ids,
        "developer_envs": stale_env_ids,
        "bench_jobs": stale_job_ids,
    }


def _print_preview(preview: dict[str, list[str]], *, stale_after_seconds: int) -> None:
    counts = {key: len(ids) for key, ids in preview.items()}
    total = sum(counts.values())
    if total == 0:
        print(f"No stale rows (stale_after_seconds={stale_after_seconds}).")
        return

    print(f"Would fail {total} row(s) (stale_after_seconds={stale_after_seconds}):")
    for kind, ids in preview.items():
        if not ids:
            continue
        sample = ", ".join(ids[:5])
        suffix = f" … +{len(ids) - 5} more" if len(ids) > 5 else ""
        print(f"  {kind}: {len(ids)} ({sample}{suffix})")


async def _run(*, stale_after_seconds: int, dry_run: bool) -> int:
    from bench_common.storage import database as db

    preview = await _preview_stale(stale_after_seconds=stale_after_seconds)
    _print_preview(preview, stale_after_seconds=stale_after_seconds)
    if dry_run or sum(len(v) for v in preview.values()) == 0:
        return 0

    result = await db.reap_stale_work(
        stale_after_seconds=stale_after_seconds,
        reason="manual_reap",
    )
    print(
        "Reaped:",
        ", ".join(f"{key}={count}" for key, count in result.items() if count),
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mark stale pending/running bench rows as failed.",
    )
    parser.add_argument(
        "--stale-after-seconds",
        type=int,
        default=0,
        help="Only fail rows older than N seconds (0 = all in-flight rows). Default: 0",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be reaped without writing to the database.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    args = parser.parse_args()

    if args.stale_after_seconds < 0:
        parser.error("--stale-after-seconds must be >= 0")

    _bootstrap_paths()
    _bootstrap_django()

    if not args.dry_run and not args.yes:
        age = args.stale_after_seconds
        if age == 0:
            prompt = "Fail ALL pending/running bench rows? [y/N] "
        else:
            prompt = f"Fail bench rows older than {age}s? [y/N] "
        answer = input(prompt).strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            raise SystemExit(1)

    raise SystemExit(asyncio.run(_run(stale_after_seconds=args.stale_after_seconds, dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
