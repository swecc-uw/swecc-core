"""
BenchAnything MCP — tools map to the HTTP API in src.api (v1 domains, runs, test).
"""
from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP

from bench_anything_mcp.artifacts import compile_benchmark_artifacts, sha256_digest
from bench_anything_mcp.client import BenchAnythingClient
from bench_anything_mcp.infer import (
    ScoringSource,
    build_domain_payload,
    shape_from_hint,
    suggest_benchmark_shape as infer_suggest_benchmark_shape,
)
from bench_anything_mcp.settings import settings
from bench_anything_mcp import validation

mcp = FastMCP("BenchAnything")

_client: BenchAnythingClient | None = None


def get_client() -> BenchAnythingClient:
    global _client
    if _client is None:
        _client = BenchAnythingClient()
    return _client


def _http_error(exc: httpx.HTTPStatusError) -> dict[str, Any]:
    body = exc.response.text
    try:
        detail = exc.response.json()
    except Exception:
        detail = body
    return {
        "ok": False,
        "error": "http_error",
        "status_code": exc.response.status_code,
        "detail": detail,
    }


# ── Hackathon / inference helpers (no API) ─────────────────────────────


@mcp.tool(name="suggest_benchmark_shape")
def suggest_benchmark_shape(plain_description: str) -> dict[str, Any]:
    """
    Recommend benchmark_kind, scoring_source (terminal vs episode_reward), and max_steps
    from a short description. Heuristic only — not an LLM.
    """
    s = infer_suggest_benchmark_shape(plain_description)
    return {
        "benchmark_kind": s.benchmark_kind,
        "scoring_source": s.scoring_source,
        "max_steps": s.max_steps,
        "primary_metric": s.primary_metric,
        "reasoning": s.reasoning,
        "tags": s.tags,
    }


@mcp.tool()
def get_constraints() -> dict[str, Any]:
    """
    Return hackathon / event constraints: allowed model prefixes, required register fields, rules version.
    Editable files live under the MCP package `rules/` directory.
    """
    c = validation.load_constraints()
    return {
        "rules_dir": str(settings.rules_dir),
        "constraints": c,
    }


@mcp.tool()
def get_theme() -> str:
    """Narrative theme, challenge ideas, and what judges value (markdown)."""
    return validation.read_markdown("theme.md")


@mcp.tool()
def get_judging_criteria() -> str:
    """Scoring rubric and weights (markdown)."""
    return validation.read_markdown("judging_criteria.md")


@mcp.tool()
def get_resources() -> str:
    """Approved APIs, credits, tools (markdown)."""
    return validation.read_markdown("resources.md")


@mcp.tool()
def validate_benchmark_config(
    domain_payload_json: str,
) -> dict[str, Any]:
    """
    Validate a proposed domain / benchmark JSON before registering. Pass the same object
    you would send to the BenchAnything POST /v1/domains (optionally with inferred_agent
    to check model allowlist).
    """
    payload = json.loads(domain_payload_json)
    return validation.validate_benchmark_config(payload)


# ── Benchmark registry (POST /v1/domains) ───────────────────────────────


@mcp.tool()
async def register_benchmark(
    benchmark_id: str,
    name: str,
    owner_id: str,
    description: str,
    env_url: str,
    max_steps: int | None = None,
    scoring_source: str | None = None,
    benchmark_kind: str | None = None,
    domain_json: str | None = None,
) -> dict[str, Any]:
    """
    Register a new draft domain (bench 'benchmark' in the protocol).
    Resolves to POST /v1/domains. If domain_json is omitted, builds a minimal binding vow
    + scoring from `description` and optional `benchmark_kind` hint.
    """
    c = get_client()
    if domain_json:
        body: dict[str, Any] = json.loads(domain_json)
    else:
        src: ScoringSource | None = None
        if scoring_source in ("terminal", "episode_reward"):
            src = scoring_source
        elif scoring_source is not None and scoring_source != "":
            return {
                "ok": False,
                "error": "invalid_scoring_source",
                "detail": "Use 'terminal' or 'episode_reward', or leave empty for inference",
            }
        shape = shape_from_hint(benchmark_kind, description)
        body = build_domain_payload(
            benchmark_id=benchmark_id,
            name=name,
            owner_id=owner_id,
            description=description,
            env_url=env_url,
            shape=shape,
            max_steps_override=max_steps,
            scoring_source_override=src,
        )
    v = validation.validate_benchmark_config(body)
    if not v.get("ok"):
        return {
            "ok": False,
            "error": "validation_failed",
            "validation": v,
            "message": "Fix issues or set BENCH_ANYTHING rules for your org — payload not sent.",
        }
    try:
        created = await c.upsert_domain(body)
    except httpx.HTTPStatusError as e:
        return _http_error(e)
    return {
        "ok": True,
        "domain": created,
        "note": "POST /v1/domains, or PATCH /v1/domains/{id} if the id already exists (draft only).",
    }


@mcp.tool()
async def publish_benchmark(benchmark_id: str) -> dict[str, Any]:
    """
    Publish a domain — makes the binding vow immutable for runs. Resolves to
    POST /v1/domains/{id}/publish. Returns digests of synthesized contract/artifact JSON.
    """
    c = get_client()
    try:
        domain = await c.publish_domain(benchmark_id)
    except httpx.HTTPStatusError as e:
        return _http_error(e)
    arts = compile_benchmark_artifacts(domain)
    digests = {name: sha256_digest(content) for name, content in arts.items()}
    return {
        "ok": True,
        "domain": domain,
        "artifact_digests": digests,
        "note": "contract.json and related artifacts are derived from the Domain object; "
        "see get_benchmark.",
    }


@mcp.tool()
async def get_benchmark(benchmark_id: str) -> dict[str, Any]:
    """
    Return compiled view of a domain: binding vow (as contract.json), eval profile, and dataset lock placeholder.
    Resolves to GET /v1/domains/{id}.
    """
    c = get_client()
    try:
        domain = await c.get_domain(benchmark_id)
    except httpx.HTTPStatusError as e:
        return _http_error(e)
    arts = compile_benchmark_artifacts(domain)
    digests = {name: sha256_digest(content) for name, content in arts.items()}
    return {
        "ok": True,
        "artifact_digests": digests,
        "artifacts": arts,
        "raw_domain": domain,
    }


@mcp.tool()
async def list_benchmarks(
    status: Literal["all", "published", "draft"] = "all",
) -> dict[str, Any]:
    """
    List registered domains. Resolves to GET /v1/domains with optional server-side published filter;
    draft filtering is client-side.
    """
    c = get_client()
    try:
        if status == "published":
            items = await c.list_domains(published_only=True)
        else:
            items = await c.list_domains(published_only=None)
    except httpx.HTTPStatusError as e:
        return _http_error(e)
    if status == "draft":
        items = [d for d in items if d.get("status") == "draft"]
    return {"ok": True, "benchmarks": items, "count": len(items)}


# ── Eval execution ───────────────────────────────────────────────────────


@mcp.tool()
async def run_dev_eval(
    domain_id: str,
    binding_vow_version: str,
    model: str,
    env_url: str | None = None,
    seed: int | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """
    One-off test episode (fast iteration). Resolves to POST /v1/test/episode.
    """
    c = get_client()
    body: dict[str, Any] = {
        "domain_id": domain_id,
        "binding_vow_version": binding_vow_version,
        "agent_config": {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    }
    if env_url is not None:
        body["env_url"] = env_url
    if seed is not None:
        body["seed"] = seed
    try:
        ep = await c.test_episode(body)
    except httpx.HTTPStatusError as e:
        return _http_error(e)
    return {"ok": True, "episode": ep, "note": "dev eval (single episode) via /v1/test/episode"}


@mcp.tool()
async def run_private_eval(
    domain_id: str,
    binding_vow_version: str,
    model: str,
    require_published: bool = True,
    num_episodes: int = 1,
    seed_set_json: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    max_parallel: int = 1,
) -> dict[str, Any]:
    """
    Full run with scoring aggregation (use after publish for frozen contracts).
    Resolves to POST /v1/runs. If require_published, rejects non-published domains.
    """
    c = get_client()
    if require_published:
        try:
            dom = await c.get_domain(domain_id)
        except httpx.HTTPStatusError as e:
            return _http_error(e)
        if dom.get("status") != "published":
            return {
                "ok": False,
                "error": "domain_not_published",
                "detail": f"Status is {dom.get('status')!r}. Set require_published=false for draft testing via runs.",
            }
    seeds: list[int] | None = None
    if seed_set_json:
        seeds = json.loads(seed_set_json)
    body: dict[str, Any] = {
        "domain_id": domain_id,
        "binding_vow_version": binding_vow_version,
        "agent_config": {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        "num_episodes": num_episodes,
        "max_parallel": max_parallel,
    }
    if seeds is not None:
        body["seed_set"] = seeds
    try:
        run = await c.create_run(body)
    except httpx.HTTPStatusError as e:
        return _http_error(e)
    return {"ok": True, "run": run, "note": "private multi-episode run via /v1/runs"}


# ── Results & inspection ────────────────────────────────────────────────


@mcp.tool()
async def get_run_results(run_id: str) -> dict[str, Any]:
    """
    Run status, per-episode summary, and aggregate scores. Uses GET /v1/runs/{id} and
    GET /v1/runs/{id}/episodes (the API has no /results path yet; this is an MCP aggregate).
    """
    c = get_client()
    try:
        run = await c.get_run(run_id)
        episodes = await c.list_episodes(run_id)
    except httpx.HTTPStatusError as e:
        return _http_error(e)
    digest = sha256_digest(
        {
            "run_id": run_id,
            "status": run.get("status"),
            "scores": run.get("scores", {}),
            "episodes": [e.get("id") for e in episodes],
        }
    )
    return {
        "ok": True,
        "run": run,
        "episodes": episodes,
        "aggregate_scores": run.get("scores", {}),
        "result_digest": digest,
    }


@mcp.tool()
async def get_run_episodes(
    run_id: str,
    include_traces: bool = False,
) -> dict[str, Any]:
    """
    Episodes for a run, optionally with full per-episode event traces. Uses GET
    /v1/runs/{id}/episodes and, when include_traces is true, GET /v1/runs/{id}/traces.
    """
    c = get_client()
    try:
        episodes = await c.list_episodes(run_id)
        traces: dict[str, Any] = {}
        if include_traces:
            traces = await c.get_run_traces(run_id)
    except httpx.HTTPStatusError as e:
        return _http_error(e)
    return {
        "ok": True,
        "run_id": run_id,
        "episodes": episodes,
        "traces_by_episode": traces,
    }


@mcp.tool()
async def cancel_run(run_id: str) -> dict[str, Any]:
    """
    Cancel an in-flight run. The current BenchAnything HTTP API has no run cancel endpoint
    (episodes are scheduled locally); this tool documents that contract for clients.
    """
    return {
        "ok": False,
        "error": "not_implemented",
        "run_id": run_id,
        "detail": "The BenchAnything API does not expose POST /v1/runs/{id}/cancel yet.",
    }
