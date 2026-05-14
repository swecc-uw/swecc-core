from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

ScoringSource = Literal["terminal", "episode_reward"]


@dataclass(frozen=True)
class SuggestedShape:
    benchmark_kind: str
    scoring_source: ScoringSource
    max_steps: int
    reasoning: str
    primary_metric: str
    tags: list[str]


_QA = re.compile(
    r"\b(trivia|quiz|question|choice|mcq|multiple\s*choice|answer\s*[abcd])\b", re.I
)
_MULTI = re.compile(
    r"\b(wordle|game|level|maze|simulation|grid|turn|round|multi[- ]?step|episode|rl)\b", re.I
)
_TOOL = re.compile(r"\b(tool|function\s*call|mcp|api|search)\b", re.I)


def suggest_benchmark_shape(plain_description: str) -> SuggestedShape:
    """
    Heuristic (no LLM) — nudges teams toward a defensible default contract.
    """
    t = plain_description.strip()
    tags: list[str] = ["heuristic_suggestion"]
    if _QA.search(t) and not _MULTI.search(t):
        return SuggestedShape(
            benchmark_kind="qa_mcq",
            scoring_source="terminal",
            max_steps=1,
            reasoning=(
                "Description looks like single-shot Q/A or multiple choice. "
                "Defaulting to max_steps=1 and terminal-based scoring (success/correct in info)."
            ),
            primary_metric="success_rate",
            tags=tags + ["qa", "mcq"],
        )
    if _TOOL.search(t):
        tags.append("tools")
    if _MULTI.search(t) or len(t) > 400:
        return SuggestedShape(
            benchmark_kind="interactive_env",
            scoring_source="episode_reward",
            max_steps=50,
            reasoning=(
                "Description suggests multi-step interaction or a heavier task. "
                "Defaulting to max_steps=50 and reward-based primary scoring; "
                "tighten max_steps to your environment's true horizon."
            ),
            primary_metric="avg_reward",
            tags=tags + ["env", "multi_step"],
        )
    return SuggestedShape(
        benchmark_kind="general_text_env",
        scoring_source="terminal",
        max_steps=30,
        reasoning=(
            "No strong signal — using a small multi-step default with terminal success "
            "as primary. Adjust if your env is single-shot or long-horizon."
        ),
        primary_metric="success_rate",
        tags=tags + ["default"],
    )


def shape_from_hint(
    benchmark_kind: str | None,
    description: str,
) -> SuggestedShape:
    if not benchmark_kind:
        return suggest_benchmark_shape(description)
    k = benchmark_kind.lower().strip()
    if k in ("qa_mcq", "qa", "trivia", "quiz"):
        return suggest_benchmark_shape("trivia quiz question multiple choice " + description)
    if k in ("interactive_env", "interactive", "env", "multi_step", "game"):
        return suggest_benchmark_shape("multi step game simulation episode " + description)
    return suggest_benchmark_shape(f"{k} " + description)


def build_domain_payload(
    *,
    benchmark_id: str,
    name: str,
    owner_id: str,
    description: str,
    env_url: str,
    shape: SuggestedShape | None = None,
    max_steps_override: int | None = None,
    scoring_source_override: ScoringSource | None = None,
) -> dict[str, Any]:
    """
    Assembles a POST /v1/domains body (domain JSON) consistent with BenchAnything.
    """
    s = shape or suggest_benchmark_shape(description)
    scoring_source: ScoringSource = scoring_source_override or s.scoring_source
    max_steps = max_steps_override if max_steps_override is not None else s.max_steps
    max_steps = max(1, min(max_steps, 1_000_000))

    vow_id = f"{benchmark_id}-vow-1"
    if scoring_source == "terminal":
        metrics = [
            {
                "name": s.primary_metric,
                "type": "terminal_field",
                "field": "success",
                "aggregation": "pass_rate",
            },
            {"name": "avg_reward", "type": "episode_reward", "aggregation": "mean"},
        ]
        primary_metric_name = s.primary_metric
    else:
        metrics = [
            {
                "name": "avg_reward",
                "type": "episode_reward",
                "aggregation": "mean",
            },
            {"name": "success_rate", "type": "terminal_field", "field": "success", "aggregation": "pass_rate"},
        ]
        primary_metric_name = "avg_reward"

    binding_vow: dict[str, Any] = {
        "id": vow_id,
        "version": "1.0.0",
        "domain_id": benchmark_id,
        "tier": "tier1",
        "description": description,
        "observation_space": {
            "type": "text",
            "description": "Environment observation (UTF-8 text or encoded task description).",
        },
        "action_space": {
            "type": "text",
            "description": "Free-form string action; refine to json/discrete in domain.py for production.",
        },
        "reward": {"type": "scalar", "description": "Step reward; env may also set terminal info."},
        "episode": {
            "max_steps": max_steps,
            "supports_seed": True,
            "deterministic_reset": True,
        },
        "techniques": [],
        "metadata": {
            "benchmark_kind": s.benchmark_kind,
            "mcp_inferred": True,
        },
    }

    scoring: dict[str, Any] = {
        "primary_metric": primary_metric_name,
        "higher_is_better": True,
        "metrics": metrics,
    }

    return {
        "id": benchmark_id,
        "name": name,
        "owner_id": owner_id,
        "binding_vow": binding_vow,
        "endpoint": {"mode": "remote", "url": env_url},
        "scoring": scoring,
        "tags": s.tags,
        "detail": description,
    }
