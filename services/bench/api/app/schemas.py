"""API response DTOs (slimmer than bench_common core models for list surfaces)."""

from __future__ import annotations

from bench_common.core.run import Run
from pydantic import BaseModel


class RunEpisodeSummary(BaseModel):
    completed_count: int = 0
    failed_count: int = 0
    truncated_count: int = 0
    cancelled_count: int = 0
    timeout_count: int = 0
    avg_reward: float | None = None
    failure_reasons: list[str] = []
    truncation_reasons: list[str] = []
    cancellation_reasons: list[str] = []


class RunListItem(Run):
    """Run row for list endpoints with optional episode aggregates."""

    completed_count: int = 0
    failed_count: int = 0
    truncated_count: int = 0
    cancelled_count: int = 0
    timeout_count: int = 0
    avg_reward: float | None = None
    failure_reasons: list[str] = []
    truncation_reasons: list[str] = []
    cancellation_reasons: list[str] = []
    actor_type: str | None = None
    actor_id: str | None = None
    actor_username: str | None = None
    visibility: str | None = None


class DomainListItem(BaseModel):
    id: str
    name: str
    tags: list[str] = []
    image: str | None = None


class DomainEnvironmentListItem(BaseModel):
    """Slim env row for domain detail (fetch via GET /v1/domains/{id}/environments)."""

    id: str
    name: str
    status: str
    domain_id: str | None
    env_url: str | None
    scope: str
    team_id: str | None = None


class DomainActivityItem(RunListItem):
    source: str  # "mine" | "gallery"


class DomainActivityResponse(BaseModel):
    items: list[DomainActivityItem]
    next_cursor: str | None = None


class MeWithContextResponse(BaseModel):
    type: str
    user_id: int | None = None
    username: str | None = None
    guest_session_id: str | None = None
    context: dict | None = None


class RunStatusItem(BaseModel):
    """Lightweight run row for batch status polling."""

    id: str
    status: str
    scores: dict[str, float] = {}
    completed_at: str | None = None
    status_reason: str | None = None
    status_detail: dict = {}
    truncated_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0
    truncation_reasons: list[str] = []
    failure_reasons: list[str] = []


class RunStatusBatchResponse(BaseModel):
    runs: dict[str, RunStatusItem]


# Pagination caps (documented on OpenAPI query params)
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100
DEFAULT_DEV_ENV_RUNS_LIMIT = 10
MAX_DEV_ENV_RUNS_LIMIT = 50
DEFAULT_LEADERBOARD_LIMIT = 50
MAX_LEADERBOARD_LIMIT = 100
