"""
Domain for the 2048 environment (4x4, slide and merge, win at 2048 tile).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from bench_common.core.binding_vow import (
    BindingVow,
    EpisodeSemantics,
    RewardSpec,
    SpaceSpec,
    SpaceType,
)
from bench_common.core.domain import EnvironmentEndpoint
from bench_common.core.scoring import MetricDef, ScoringConfig
from bench_common.env_sdk.registration import DomainConfig

DOMAIN_ID = "game-2048"
DOMAIN_NAME = "2048 (4x4)"
OWNER_ID = "local-dev"
ADAPTER_URL = "http://localhost:8765"
TAGS = ["game", "2048", "planning", "tier1"]

BINDING_VOW = BindingVow(
    id="game-2048-v1",
    version="1.0.0",
    domain_id=DOMAIN_ID,
    tier="tier1",
    description=(
        "2048 on a 4x4 board. The observation is JSON: { grid, score, step, target, size, message }. "
        "Each turn choose one action: up, down, left, or right. "
        "The episode ends with success when a tile's value reaches 2048, failure when there is no legal move, "
        "or truncation when the step cap is hit."
    ),
    observation_space=SpaceSpec(
        type=SpaceType.JSON,
        description=(
            '{ "grid": 4x4 of ints (0=empty, powers of 2), "score": int, "step": int, '
            '"target": 2048, "size": 4, "message": str }'
        ),
    ),
    action_space=SpaceSpec(
        type=SpaceType.DISCRETE,
        enum_values=["up", "down", "left", "right"],
        description="One move per turn (also accepts l/r/u/d).",
    ),
    reward=RewardSpec(
        type="scalar",
        range={"low": -1.0, "high": 1_200.0},
        description="Merge score delta; win bonus +1000; invalid move penalty -0.1",
    ),
    episode=EpisodeSemantics(
        max_steps=5_000,
        supports_seed=True,
        deterministic_reset=True,
    ),
    techniques=[],
)

SCORING = ScoringConfig(
    primary_metric="win_rate",
    higher_is_better=True,
    metrics=[
        MetricDef(
            name="win_rate",
            type="terminal_field",
            field="won",
            aggregation="pass_rate",
        ),
        MetricDef(
            name="avg_max_tile",
            type="terminal_field",
            field="max_tile",
            aggregation="mean",
        ),
        MetricDef(
            name="avg_score",
            type="terminal_field",
            field="score",
            aggregation="mean",
        ),
        MetricDef(
            name="avg_reward",
            type="episode_reward",
            aggregation="mean",
        ),
    ],
)

DOMAIN_CONFIG = DomainConfig(
    id=DOMAIN_ID,
    name=DOMAIN_NAME,
    owner_id=OWNER_ID,
    binding_vow=BINDING_VOW,
    endpoint=EnvironmentEndpoint(mode="remote", url=ADAPTER_URL),
    scoring=SCORING,
    tags=TAGS,
)
