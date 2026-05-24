"""
SQLite storage backend — zero-dependency alternative to the Django/Postgres backend.

Enabled by setting ORCH_DB_BACKEND=sqlite.  Tables are created on the first
init_db() call; no migration step is required.  Designed for local development
and CI testing where a running Postgres server is unavailable.

Schema mirrors the Django models in services/server/server/bench/models.py so
data written here is structurally identical to production.  When you're ready
to move to Supabase, point ORCH_DB_BACKEND=django (or add a supabase backend)
and re-run migrations — the Pydantic models that sit on top of both backends
are unchanged.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import aiosqlite
from bench_common.config import settings
from bench_common.core.domain import Domain
from bench_common.core.run import Episode, Run

_DDL = """
CREATE TABLE IF NOT EXISTS bench_domain (
    id        TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    published INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bench_run (
    id        TEXT PRIMARY KEY,
    domain_id TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'pending',
    data      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bench_episode (
    id     TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    data   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bench_developerenvironment (
    id            TEXT PRIMARY KEY,
    owner_id      TEXT NOT NULL,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    github_url    TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'pending',
    domain_id     TEXT,
    env_url       TEXT,
    error_message TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bench_benchjob (
    id             TEXT PRIMARY KEY,
    environment_id TEXT NOT NULL,
    domain_id      TEXT,
    github_url     TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'queued',
    model_results  TEXT,
    claimed_at     TEXT,
    completed_at   TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bench_leaderboard (
    id            TEXT PRIMARY KEY,
    domain_id     TEXT NOT NULL,
    run_id        TEXT NOT NULL UNIQUE,
    model         TEXT NOT NULL,
    primary_score REAL,
    data          TEXT NOT NULL
);
"""


def _db_path() -> str:
    return settings.sqlite_path


async def _connect() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(_db_path())
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def init_db() -> None:
    """Create all tables if they don't exist yet.  Safe to call on every startup."""
    async with await _connect() as conn:
        await conn.executescript(_DDL)
        await conn.commit()


# ── Domain ────────────────────────────────────────────────────────────────────


async def save_domain(domain: Domain) -> None:
    async with await _connect() as conn:
        await conn.execute(
            """
            INSERT INTO bench_domain (id, data, published)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                data      = excluded.data,
                published = excluded.published
            """,
            (domain.id, domain.model_dump_json(), 1 if domain.status == "published" else 0),
        )
        await conn.commit()


async def get_domain(domain_id: str) -> Domain | None:
    async with await _connect() as conn:
        async with conn.execute("SELECT data FROM bench_domain WHERE id = ?", (domain_id,)) as cur:
            row = await cur.fetchone()
    return Domain.model_validate_json(row["data"]) if row else None


async def list_domains(*, published_only: bool = False) -> list[Domain]:
    sql = "SELECT data FROM bench_domain"
    params: tuple = ()
    if published_only:
        sql += " WHERE published = 1"
    async with await _connect() as conn:
        async with conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [Domain.model_validate_json(r["data"]) for r in rows]


# ── Run ───────────────────────────────────────────────────────────────────────


async def save_run(run: Run) -> None:
    async with await _connect() as conn:
        await conn.execute(
            """
            INSERT INTO bench_run (id, domain_id, status, data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                domain_id = excluded.domain_id,
                status    = excluded.status,
                data      = excluded.data
            """,
            (run.id, run.config.domain_id, run.status, run.model_dump_json()),
        )
        await conn.commit()


async def get_run(run_id: str) -> Run | None:
    async with await _connect() as conn:
        async with conn.execute("SELECT data FROM bench_run WHERE id = ?", (run_id,)) as cur:
            row = await cur.fetchone()
    return Run.model_validate_json(row["data"]) if row else None


async def list_runs(domain_id: str | None = None) -> list[Run]:
    sql = "SELECT data FROM bench_run"
    params: tuple = ()
    if domain_id:
        sql += " WHERE domain_id = ?"
        params = (domain_id,)
    async with await _connect() as conn:
        async with conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [Run.model_validate_json(r["data"]) for r in rows]


# ── Episode ───────────────────────────────────────────────────────────────────


async def save_episode(episode: Episode) -> None:
    async with await _connect() as conn:
        await conn.execute(
            """
            INSERT INTO bench_episode (id, run_id, status, data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                run_id = excluded.run_id,
                status = excluded.status,
                data   = excluded.data
            """,
            (episode.id, episode.run_id, episode.status, episode.model_dump_json()),
        )
        await conn.commit()


async def get_episode(episode_id: str) -> Episode | None:
    async with await _connect() as conn:
        async with conn.execute(
            "SELECT data FROM bench_episode WHERE id = ?", (episode_id,)
        ) as cur:
            row = await cur.fetchone()
    return Episode.model_validate_json(row["data"]) if row else None


async def get_episodes(run_id: str) -> list[Episode]:
    async with await _connect() as conn:
        async with conn.execute(
            "SELECT data FROM bench_episode WHERE run_id = ?", (run_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [Episode.model_validate_json(r["data"]) for r in rows]


# ── Developer Environments ────────────────────────────────────────────────────


async def save_developer_environment(env: dict[str, Any]) -> None:
    async with await _connect() as conn:
        await conn.execute(
            """
            INSERT INTO bench_developerenvironment
                (id, owner_id, name, description, github_url, status,
                 domain_id, env_url, error_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                owner_id      = excluded.owner_id,
                name          = excluded.name,
                description   = excluded.description,
                github_url    = excluded.github_url,
                status        = excluded.status,
                domain_id     = excluded.domain_id,
                env_url       = excluded.env_url,
                error_message = excluded.error_message
            """,
            (
                env["id"],
                env["owner_id"],
                env["name"],
                env.get("description", ""),
                env.get("github_url", ""),
                env.get("status", "pending"),
                env.get("domain_id"),
                env.get("env_url"),
                env.get("error_message"),
                env.get("created_at", datetime.utcnow().isoformat()),
            ),
        )
        await conn.commit()


async def get_developer_environment(env_id: str) -> dict[str, Any] | None:
    async with await _connect() as conn:
        async with conn.execute(
            "SELECT * FROM bench_developerenvironment WHERE id = ?", (env_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def delete_developer_environment(env_id: str) -> bool:
    async with await _connect() as conn:
        cur = await conn.execute("DELETE FROM bench_developerenvironment WHERE id = ?", (env_id,))
        await conn.commit()
    return cur.rowcount > 0


async def list_developer_environments(owner_id: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM bench_developerenvironment ORDER BY created_at DESC"
    params: tuple = ()
    if owner_id:
        sql = (
            "SELECT * FROM bench_developerenvironment WHERE owner_id = ? "
            "ORDER BY created_at DESC"
        )
        params = (owner_id,)
    async with await _connect() as conn:
        async with conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── Environment Usage ─────────────────────────────────────────────────────────


async def get_domain_usage_stats(domain_id: str) -> dict[str, Any]:
    async with await _connect() as conn:
        async with conn.execute(
            "SELECT data FROM bench_run WHERE domain_id = ?", (domain_id,)
        ) as cur:
            run_rows = await cur.fetchall()
        async with conn.execute(
            "SELECT primary_score FROM bench_leaderboard WHERE domain_id = ?", (domain_id,)
        ) as cur:
            lb_rows = await cur.fetchall()

    total_runs = len(run_rows)
    total_episodes = 0
    for r in run_rows:
        run = Run.model_validate_json(r["data"])
        total_episodes += run.config.num_episodes if run.config else 0

    scores = [r["primary_score"] for r in lb_rows if r["primary_score"] is not None]
    return {
        "domain_id": domain_id,
        "total_runs": total_runs,
        "total_episodes": total_episodes,
        "avg_score": sum(scores) / len(scores) if scores else None,
        "best_score": max(scores) if scores else None,
        "leaderboard_entries": len(lb_rows),
    }


# ── Bench Jobs ────────────────────────────────────────────────────────────────


async def create_bench_job(env_id: str, domain_id: str | None, github_url: str) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with await _connect() as conn:
        await conn.execute(
            """
            INSERT INTO bench_benchjob
                (id, environment_id, domain_id, github_url, status, created_at)
            VALUES (?, ?, ?, ?, 'queued', ?)
            """,
            (job_id, env_id, domain_id, github_url, now),
        )
        await conn.commit()
    job = await get_bench_job(job_id)
    assert job is not None
    return job


async def get_bench_job(job_id: str) -> dict[str, Any] | None:
    async with await _connect() as conn:
        async with conn.execute("SELECT * FROM bench_benchjob WHERE id = ?", (job_id,)) as cur:
            row = await cur.fetchone()
    return _job_row_to_dict(dict(row)) if row else None


async def list_bench_jobs(
    env_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if env_id:
        clauses.append("environment_id = ?")
        params.append(env_id)
    if status:
        clauses.append("status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM bench_benchjob {where} ORDER BY created_at DESC"

    async with await _connect() as conn:
        async with conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
    return [_job_row_to_dict(dict(r)) for r in rows]


async def claim_bench_job(job_id: str) -> dict[str, Any] | None:
    """Atomically transition a job from queued → running.

    Uses BEGIN IMMEDIATE to prevent concurrent claims on SQLite (equivalent to
    SELECT FOR UPDATE SKIP LOCKED on Postgres).
    """
    now = datetime.utcnow().isoformat()
    async with await _connect() as conn:
        await conn.execute("BEGIN IMMEDIATE")
        try:
            async with conn.execute(
                "SELECT id FROM bench_benchjob WHERE id = ? AND status = 'queued'", (job_id,)
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                await conn.execute("ROLLBACK")
                return None
            await conn.execute(
                "UPDATE bench_benchjob SET status = 'running', claimed_at = ? WHERE id = ?",
                (now, job_id),
            )
            await conn.commit()
        except Exception:
            await conn.execute("ROLLBACK")
            raise

    return await get_bench_job(job_id)


async def complete_bench_job(
    job_id: str, model_results: dict[str, Any], failed: bool = False
) -> dict[str, Any] | None:
    status = "failed" if failed else "completed"
    now = datetime.utcnow().isoformat()
    async with await _connect() as conn:
        cur = await conn.execute(
            "UPDATE bench_benchjob SET status = ?, model_results = ?, completed_at = ? WHERE id = ?",
            (status, json.dumps(model_results), now, job_id),
        )
        await conn.commit()
    return await get_bench_job(job_id) if cur.rowcount > 0 else None


def _job_row_to_dict(row: dict) -> dict[str, Any]:
    results = row.get("model_results")
    if isinstance(results, str) and results:
        results = json.loads(results)
    return {
        "id": row["id"],
        "env_id": row["environment_id"],
        "domain_id": row.get("domain_id"),
        "github_url": row["github_url"],
        "status": row["status"],
        "model_results": results,
        "claimed_at": row.get("claimed_at"),
        "completed_at": row.get("completed_at"),
        "created_at": row.get("created_at"),
    }
