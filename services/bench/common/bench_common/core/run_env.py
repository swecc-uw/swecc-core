"""Run ↔ developer environment helpers (no Django imports)."""

from __future__ import annotations

from typing import Any

from bench_common.core.run import Run


def validate_env_domain_match(env: dict[str, Any] | None, env_id: str, domain_id: str) -> None:
    if env is None:
        raise ValueError(f"Environment '{env_id}' not found")
    if env.get("domain_id") != domain_id:
        raise ValueError(
            f"Environment '{env_id}' is linked to domain {env.get('domain_id')!r}, "
            f"not {domain_id!r}"
        )


def merge_run_env_id(run: Run, row_env_id: str | None) -> Run:
    if row_env_id and run.env_id != row_env_id:
        return run.model_copy(update={"env_id": row_env_id})
    return run
