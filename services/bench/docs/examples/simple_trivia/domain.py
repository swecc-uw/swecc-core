"""
Domain configuration for the simple trivia environment.

Edit the constants at the top, then run register.py to push this to
the platform.  You only need to re-run register.py when you change
the domain metadata — the adapter server (adapter.py) is independent.
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

# ── Edit these ────────────────────────────────────────────────────────────────

DOMAIN_ID = "simple-trivia"
DOMAIN_NAME = "Simple Trivia Quiz"
OWNER_ID = "your-username"  # set this to your user/org id
ADAPTER_URL = "http://localhost:8765"  # where adapter.py is running
TAGS = ["nlp", "multiple-choice", "tier1"]

# ── Binding Vow — describes the env contract ──────────────────────────────────

BINDING_VOW = BindingVow(
    id="simple-trivia-v1",
    version="1.0.0",
    domain_id=DOMAIN_ID,
    tier="tier1",
    description=(
        "Multiple-choice trivia quiz. "
        "The agent receives a question + four labelled choices and must "
        "respond with the single letter of the correct answer (A/B/C/D)."
    ),
    observation_space=SpaceSpec(
        type=SpaceType.JSON,
        description='{ "question": str, "choices": { "A": str, "B": str, "C": str, "D": str } }',
    ),
    action_space=SpaceSpec(
        type=SpaceType.DISCRETE,
        enum_values=["A", "B", "C", "D"],
        description="Single answer letter",
    ),
    reward=RewardSpec(
        type="binary",
        range={"low": 0.0, "high": 1.0},
        description="1 if the chosen letter matches the correct answer, 0 otherwise",
    ),
    episode=EpisodeSemantics(
        max_steps=1,
        supports_seed=True,
        deterministic_reset=True,
    ),
    techniques=[],  # no techniques needed for a single-step env
)

# ── Scoring ───────────────────────────────────────────────────────────────────

SCORING = ScoringConfig(
    primary_metric="accuracy",
    higher_is_better=True,
    metrics=[
        MetricDef(
            name="accuracy",
            type="terminal_field",
            field="correct",  # env sets info["correct"] = "True"/"False"
            aggregation="pass_rate",
        ),
        MetricDef(
            name="avg_reward",
            type="episode_reward",
            aggregation="mean",
        ),
    ],
)

# ── Combined config (used by register.py) ─────────────────────────────────────

DOMAIN_CONFIG = DomainConfig(
    id=DOMAIN_ID,
    name=DOMAIN_NAME,
    owner_id=OWNER_ID,
    binding_vow=BINDING_VOW,
    endpoint=EnvironmentEndpoint(mode="remote", url=ADAPTER_URL),
    scoring=SCORING,
    tags=TAGS,
)
