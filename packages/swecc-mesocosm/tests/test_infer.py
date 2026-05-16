from __future__ import annotations

from swecc_mesocosm.infer import build_domain_payload, suggest_benchmark_shape


def test_suggest_qa_mcq_from_trivia_description() -> None:
    s = suggest_benchmark_shape("A trivia quiz with multiple choice questions.")
    assert s.benchmark_kind == "qa_mcq"
    assert s.scoring_source == "terminal"
    assert s.max_steps == 1
    assert s.primary_metric == "success_rate"


def test_suggest_interactive_env_from_game_description() -> None:
    s = suggest_benchmark_shape("Multi-step grid game with turns and episodes.")
    assert s.benchmark_kind == "interactive_env"
    assert s.scoring_source == "episode_reward"
    assert s.primary_metric == "avg_reward"


def test_build_domain_payload_terminal_scoring() -> None:
    body = build_domain_payload(
        benchmark_id="demo-bench",
        name="Demo",
        owner_id="team-1",
        description="trivia quiz",
        env_url="https://example.com/env",
    )
    assert body["id"] == "demo-bench"
    assert body["endpoint"]["url"] == "https://example.com/env"
    assert body["binding_vow"]["episode"]["max_steps"] == 1
    metric_names = {m["name"] for m in body["scoring"]["metrics"]}
    assert body["scoring"]["primary_metric"] in metric_names


def test_build_domain_payload_clamps_max_steps() -> None:
    body = build_domain_payload(
        benchmark_id="big",
        name="Big",
        owner_id="team-1",
        description="game",
        env_url="https://example.com/env",
        max_steps_override=2_000_000,
    )
    assert body["binding_vow"]["episode"]["max_steps"] == 1_000_000
