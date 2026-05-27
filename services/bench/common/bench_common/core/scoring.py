from typing import Any, Literal

from pydantic import BaseModel, model_validator


class MetricDef(BaseModel):
    name: str
    type: Literal["episode_reward", "terminal_field", "trajectory_judge", "human_judge"]
    aggregation: Literal["mean", "median", "max", "min", "sum", "pass_rate"]
    field: str | None = None
    judge_config: dict[str, Any] | None = None
    # Used when aggregation == "pass_rate": an episode counts as a pass when its
    # value exceeds this threshold.  Defaults to 0.0 (positive reward = pass).
    # Set to a domain-specific value (e.g. 0.5 for partial-credit environments,
    # or -1.0 for negative-reward environments where any non-worst score passes).
    pass_threshold: float = 0.0


class ScoringConfig(BaseModel):
    primary_metric: str
    metrics: list[MetricDef]
    higher_is_better: bool = True

    @model_validator(mode="after")
    def _primary_metric_must_exist(self) -> "ScoringConfig":
        """Catch primary_metric typos at domain registration time, not at scoring time."""
        defined = {m.name for m in self.metrics}
        if self.primary_metric not in defined:
            raise ValueError(
                f"primary_metric {self.primary_metric!r} is not defined in the metrics list "
                f"(defined: {sorted(defined)}). "
                f"Add a MetricDef with name={self.primary_metric!r} or fix the typo."
            )
        return self
