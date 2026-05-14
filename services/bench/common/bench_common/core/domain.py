from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from bench_common.core.binding_vow import BindingVow
from bench_common.core.scoring import ScoringConfig


class ResourceSpec(BaseModel):
    cpu: str = "2"
    memory: str = "4Gi"
    gpu: str | None = None
    timeout_seconds: int = 3600


class EnvironmentEndpoint(BaseModel):
    """How the platform reaches the environment."""

    mode: Literal["remote", "sandbox"] = "remote"
    url: str | None = None
    image: str | None = None
    resources: ResourceSpec | None = None


class VersionEntry(BaseModel):
    version: str
    date: str
    changes: str


class Domain(BaseModel):
    id: str
    name: str
    owner_id: str
    binding_vow: BindingVow
    endpoint: EnvironmentEndpoint
    scoring: ScoringConfig
    status: Literal["draft", "testing", "published", "archived"] = "draft"
    tags: list[str] = []
    detail: str = ""
    pricing: str = "free"
    version_history: list[VersionEntry] = []
    image_url: str | None = None
    profile_picture_url: str | None = None
    has_gold_benchmark: bool = False
