"""
Scoring engine — computes metrics from completed episodes.
"""

from __future__ import annotations

import statistics
from typing import Any

from bench_common.core.run import Episode
from bench_common.core.scoring import MetricDef, ScoringConfig


_SCOREABLE_STATUSES = frozenset({"completed", "timeout"})


def compute_metric(metric: MetricDef, episodes: list[Episode]) -> float:
    # Only include episodes that ran to a natural conclusion.  Failed and
    # cancelled episodes have no valid reward signal and must not be mixed
    # into aggregations — a crash is not the same as a score of 0.
    scoreable = [ep for ep in episodes if ep.status in _SCOREABLE_STATUSES]
    values: list[float] = []

    for ep in scoreable:
        if metric.type == "episode_reward":
            values.append(ep.total_reward)
        elif metric.type == "terminal_field":
            if metric.field and metric.field in ep.terminal_info:
                try:
                    values.append(float(ep.terminal_info[metric.field]))
                except (TypeError, ValueError):
                    pass
        elif metric.type in ("trajectory_judge", "human_judge"):
            # Not implemented in MVP — skip
            pass

    if not values:
        return 0.0

    agg = metric.aggregation
    if agg == "mean":
        return statistics.mean(values)
    if agg == "median":
        return statistics.median(values)
    if agg == "max":
        return max(values)
    if agg == "min":
        return min(values)
    if agg == "sum":
        return sum(values)
    if agg == "pass_rate":
        return sum(1 for v in values if v > 0) / len(values)
    return statistics.mean(values)


def compute_scores(scoring: ScoringConfig, episodes: list[Episode]) -> dict[str, float]:
    return {m.name: compute_metric(m, episodes) for m in scoring.metrics}
