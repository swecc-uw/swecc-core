from __future__ import annotations

import re
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

    def validate(self) -> None:
        """Check all vow constraints.

        Raises VowViolationError listing every problem found so the author
        can fix them all in one pass rather than discovering them one at a time.
        """
        from bench_common.core.errors import VowViolationError

        problems: list[str] = []

        if not _is_valid_semver(self.version):
            problems.append(
                f"version {self.version!r} is not valid SemVer — expected 'MAJOR.MINOR.PATCH' "
                f"(e.g. '1.0.0')"
            )

        problems.extend(_check_space("observation_space", self.observation_space))
        problems.extend(_check_space("action_space", self.action_space))

        if self.reward.range:
            lo = self.reward.range.get("low")
            hi = self.reward.range.get("high")
            if lo is not None and hi is not None and lo >= hi:
                problems.append(
                    f"reward.range.low ({lo}) must be strictly less than .high ({hi})"
                )

        if self.episode.max_steps is not None and self.episode.max_steps <= 0:
            problems.append("episode.max_steps must be a positive integer when set")
        if self.episode.max_wall_seconds is not None and self.episode.max_wall_seconds <= 0:
            problems.append("episode.max_wall_seconds must be a positive integer when set")
        if self.episode.parallel_episodes < 1:
            problems.append("episode.parallel_episodes must be >= 1")

        for td in self.techniques:
            if not td.technique_id:
                problems.append("each technique declaration must have a non-empty technique_id")
            if td.version and not _is_valid_version_req(td.version):
                problems.append(
                    f"technique '{td.technique_id}' version requirement {td.version!r} is not "
                    f"valid — use SemVer or a range like '^1.0'"
                )

        if problems:
            bullet = "\n  • "
            raise VowViolationError(
                f"BindingVow '{self.id}' (v{self.version}) has "
                f"{len(problems)} violation(s):{bullet}{bullet.join(problems)}"
            )


# ── helpers ────────────────────────────────────────────────────────────────────

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+")
_VERSION_REQ_RE = re.compile(r"^[\^~]?\d+\.\d+(\.\d+)?")


def _is_valid_semver(version: str) -> bool:
    return bool(_SEMVER_RE.match(version))


def _is_valid_version_req(req: str) -> bool:
    return bool(_VERSION_REQ_RE.match(req))


def _check_space(name: str, space: "SpaceSpec | CompositeSpace") -> list[str]:
    problems: list[str] = []
    if isinstance(space, CompositeSpace):
        if not space.fields:
            problems.append(f"{name}: composite space must have at least one field")
        for field_name, sub in space.fields.items():
            problems.extend(_check_space(f"{name}.{field_name}", sub))
    else:
        if space.type == SpaceType.DISCRETE:
            if not space.enum_values:
                problems.append(f"{name}: discrete space must declare enum_values")
            elif len(set(space.enum_values)) != len(space.enum_values):
                problems.append(f"{name}: discrete enum_values contains duplicates")
        if space.type == SpaceType.CONTINUOUS and space.bounds:
            lo = space.bounds.get("low")
            hi = space.bounds.get("high")
            if lo is not None and hi is not None and lo >= hi:
                problems.append(
                    f"{name}: continuous bounds.low ({lo}) must be < bounds.high ({hi})"
                )
    return problems
