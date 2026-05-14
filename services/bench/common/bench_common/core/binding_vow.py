from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SpaceType(str, Enum):
    DISCRETE = "discrete"
    CONTINUOUS = "continuous"
    TEXT = "text"
    JSON = "json"
    IMAGE = "image"
    MULTI_MODAL = "multi_modal"
    COMPOSITE = "composite"


class SpaceSpec(BaseModel):
    """Describes one leaf of an observation or action space."""

    type: SpaceType
    dtype: str | None = None
    shape: list[int] | None = None
    bounds: dict[str, float] | None = None
    enum_values: list[str] | None = None
    schema_ref: str | None = None
    description: str = ""


class CompositeSpace(BaseModel):
    """A named dict of SpaceSpecs, for structured obs/action."""

    fields: dict[str, SpaceSpec | CompositeSpace]


class RewardSpec(BaseModel):
    type: Literal["scalar", "vector", "sparse", "binary"]
    range: dict[str, float] | None = None
    description: str = ""


class EpisodeSemantics(BaseModel):
    max_steps: int | None = None
    max_wall_seconds: int | None = None
    deterministic_reset: bool = False
    supports_seed: bool = True
    parallel_episodes: int = 1
    observability: Literal["full", "partial"] = "full"


class TechniqueDeclaration(BaseModel):
    """Declares that this Domain supports a given Technique."""

    technique_id: str
    version: str = "^1.0"
    config_schema: dict[str, Any] | None = None
    required: bool = False


class BindingVow(BaseModel):
    """
    The typed contract between a Domain and an Agent.
    Immutable once a Run references it — new versions get new IDs.
    """

    id: str = Field(..., description="Unique vow identifier, e.g. 'webarena-v2'")
    version: str = Field(..., description="SemVer string")
    domain_id: str
    tier: Literal["tier1", "tier2"]

    observation_space: SpaceSpec | CompositeSpace
    action_space: SpaceSpec | CompositeSpace
    reward: RewardSpec

    episode: EpisodeSemantics
    techniques: list[TechniqueDeclaration] = []

    metadata: dict[str, Any] = {}
    description: str = ""
