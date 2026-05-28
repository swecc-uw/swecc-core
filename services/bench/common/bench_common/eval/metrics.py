"""
Scoring engine — computes metrics from completed episodes.
"""

from __future__ import annotations

import logging
import math
import statistics

from bench_common.core.run import Episode
from bench_common.core.scoring import MetricDef, ScoringConfig

log = logging.getLogger(__name__)


def _safe_float(value: object, *, metric_name: str, episode_id: str) -> float | None:
    """Cast to float and reject NaN/inf — they would poison aggregations and
    break leaderboard sort order (NaN compares neither < nor > anything).
    """
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        log.warning(
            "metric %r: non-finite value %r from episode %s — excluded from aggregation",
            metric_name,
            out,
            episode_id,
        )
        return None
    return out


# Episodes in these terminal states produced a valid reward signal and should
# be included in scoring.  "truncated" means the step limit fired — the episode
# ran to its budget but is still scoreable.  "failed" and "cancelled" are not
# included: a crash or cancellation is not the same as a score of zero.
_SCOREABLE_STATUSES = frozenset({"completed", "timeout", "truncated"})


def compute_metric(metric: MetricDef, episodes: list[Episode]) -> float:
    scoreable = [ep for ep in episodes if ep.status in _SCOREABLE_STATUSES]
    values: list[float] = []

    for ep in scoreable:
        if metric.type == "episode_reward":
            v = _safe_float(ep.total_reward, metric_name=metric.name, episode_id=ep.id)
            if v is not None:
                values.append(v)

        elif metric.type == "terminal_field":
            if not metric.field:
                log.warning(
                    "metric %r (terminal_field) has no 'field' configured — "
                    "episode %s excluded from aggregation",
                    metric.name,
                    ep.id,
                )
                continue
            if metric.field not in ep.terminal_info:
                log.warning(
                    "terminal_field %r absent from episode %s terminal_info — "
                    "episode excluded from aggregation (available keys: %s)",
                    metric.field,
                    ep.id,
                    sorted(ep.terminal_info.keys()),
                )
                continue
            v = _safe_float(
                ep.terminal_info[metric.field], metric_name=metric.name, episode_id=ep.id
            )
            if v is not None:
                values.append(v)
            else:
                log.warning(
                    "terminal_field %r in episode %s cannot be cast to a finite float "
                    "(value=%r) — episode excluded from aggregation",
                    metric.field,
                    ep.id,
                    ep.terminal_info[metric.field],
                )

        elif metric.type in ("trajectory_judge", "human_judge"):
            # Not implemented — log loudly once per metric rather than silently
            # returning 0.0 for every episode, which would corrupt the leaderboard.
            log.warning(
                "metric %r has type %r which is not yet implemented; "
                "all episodes will score 0.0.  Use 'episode_reward' or "
                "'terminal_field' instead, or implement a judge before publishing.",
                metric.name,
                metric.type,
            )
            # Break out of the episode loop — there is nothing to compute.
            break

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
        # Count an episode as a "pass" when its value exceeds the configured
        # threshold.  Defaults to 0.0 (any positive reward = pass) but can be
        # raised for partial-credit environments or lowered for negative-reward
        # domains where even a non-worst score should count.
        threshold = metric.pass_threshold
        return sum(1 for v in values if v > threshold) / len(values)

    # Unreachable given the Literal type, but a safe fallback beats a KeyError.
    log.warning("unknown aggregation %r for metric %r — falling back to mean", agg, metric.name)
    return statistics.mean(values)


def compute_scores(scoring: ScoringConfig, episodes: list[Episode]) -> dict[str, float]:
    return {m.name: compute_metric(m, episodes) for m in scoring.metrics}
