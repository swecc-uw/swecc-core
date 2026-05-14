"""
Domain configuration for the Wordle environment.

Edit the constants at the top, then run register.py to push this to
the platform. You only need to re-run register.py when you change
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

DOMAIN_ID = "wordle"
DOMAIN_NAME = "Wordle"
OWNER_ID = "your-username"
ADAPTER_URL = "http://localhost:8888"
TAGS = ["nlp", "word-game", "tier1"]

# ── Binding Vow — describes the env contract ──────────────────────────────────

BINDING_VOW = BindingVow(
    id="wordle-v1",
    version="1.0.0",
    domain_id=DOMAIN_ID,
    tier="tier1",
    description=(
        "Classic Wordle. The agent has 6 tries to guess a 5-letter word. "
        "After each guess, it receives per-letter feedback: "
        "'green' (correct letter, correct position), 'yellow' (correct letter, "
        "wrong position), 'gray' (not in the word)."
    ),
    observation_space=SpaceSpec(
        type=SpaceType.JSON,
        description=(
            '{ "last_guess": str | null, '
            '"feedback": list[str] | null, '
            '"guesses_remaining": int }'
        ),
    ),
    action_space=SpaceSpec(
        type=SpaceType.TEXT,
        description="A 5-letter lowercase English word from the valid word list.",
    ),
    reward=RewardSpec(
        type="binary",
        range={"low": 0.0, "high": 1.0},
        description="1.0 if the agent guesses the word within 6 tries, else 0.0",
    ),
    episode=EpisodeSemantics(
        max_steps=6,
        supports_seed=True,
        deterministic_reset=True,
    ),
    techniques=[],
)

# ── Scoring ───────────────────────────────────────────────────────────────────

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
            name="avg_guesses",
            type="terminal_field",
            field="guesses_used",
            aggregation="mean",
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
