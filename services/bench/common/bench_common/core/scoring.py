from typing import Any, Literal

from pydantic import BaseModel


class MetricDef(BaseModel):
    name: str
    type: Literal["episode_reward", "terminal_field", "trajectory_judge", "human_judge"]
    aggregation: Literal["mean", "median", "max", "min", "sum", "pass_rate"]
    field: str | None = None
    judge_config: dict[str, Any] | None = None


class ScoringConfig(BaseModel):
    primary_metric: str
    metrics: list[MetricDef]
    higher_is_better: bool = True
