"""mesocosm CLI — talks to the BenchAnything HTTP API.

Run `mesocosm --help` for the command surface.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from swecc_mesocosm import validation
from swecc_mesocosm.artifacts import compile_benchmark_artifacts, sha256_digest
from swecc_mesocosm.client import BenchAnythingClient
from swecc_mesocosm.infer import ScoringSource, build_domain_payload, shape_from_hint
from swecc_mesocosm.infer import suggest_benchmark_shape as infer_suggest_benchmark_shape
from swecc_mesocosm.settings import settings

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="CLI for the BenchAnything benchmark/eval platform.",
)
eval_app = typer.Typer(no_args_is_help=True, help="Run dev or private evaluations.")
run_app = typer.Typer(no_args_is_help=True, help="Inspect existing runs.")
app.add_typer(eval_app, name="eval")
app.add_typer(run_app, name="run")

console = Console()
err_console = Console(stderr=True)


# ── helpers ────────────────────────────────────────────────────────────


def _print_json(obj: Any) -> None:
    """Pretty-print JSON to a TTY, raw to a pipe."""
    text = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    if sys.stdout.isatty():
        console.print(Syntax(text, "json", theme="ansi_dark", background_color="default"))
    else:
        sys.stdout.write(text + "\n")


def _die(msg: str, code: int = 1) -> None:
    err_console.print(f"[red]error:[/red] {msg}")
    raise typer.Exit(code)


def _http_error_payload(exc: httpx.HTTPStatusError) -> dict[str, Any]:
    body = exc.response.text
    try:
        detail = exc.response.json()
    except Exception:
        detail = body
    return {
        "error": "http_error",
        "status_code": exc.response.status_code,
        "detail": detail,
    }


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


def _client(base_url: str | None) -> BenchAnythingClient:
    return BenchAnythingClient(base_url=base_url) if base_url else BenchAnythingClient()


BaseUrlOpt = typer.Option(
    None,
    "--base-url",
    envvar="MESOCOSM_BASE_URL",
    help=f"BenchAnything API URL (default: {settings.base_url}).",
)


# ── helpers / inference (no API) ───────────────────────────────────────


@app.command("suggest")
def cmd_suggest(
    description: str = typer.Argument(..., help="Short plain-text description of the benchmark."),
) -> None:
    """Recommend benchmark_kind, scoring_source, and max_steps from a description."""
    s = infer_suggest_benchmark_shape(description)
    _print_json(
        {
            "benchmark_kind": s.benchmark_kind,
            "scoring_source": s.scoring_source,
            "max_steps": s.max_steps,
            "primary_metric": s.primary_metric,
            "reasoning": s.reasoning,
            "tags": s.tags,
        }
    )


@app.command("validate")
def cmd_validate(
    payload: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Path to a JSON file containing a POST /v1/domains body (use '-' for stdin).",
    ),
) -> None:
    """Validate a domain payload against the local policy/constraints.json."""
    if str(payload) == "-":
        raw = sys.stdin.read()
    else:
        raw = payload.read_text(encoding="utf-8")
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(f"invalid JSON: {e}")
    result = validation.validate_benchmark_config(body)
    _print_json(result)
    raise typer.Exit(0 if result.get("ok") else 1)


# ── domain CRUD ────────────────────────────────────────────────────────


@app.command("register")
def cmd_register(
    benchmark_id: str = typer.Option(..., "--id", help="Domain id (slug)."),
    name: str = typer.Option(..., "--name", help="Human-readable name."),
    owner_id: str = typer.Option(..., "--owner-id", help="Owning user/team id."),
    description: str = typer.Option(..., "--description", help="Plain-text description."),
    env_url: str = typer.Option(..., "--env-url", help="Stable HTTP URL of the eval environment."),
    max_steps: int | None = typer.Option(None, "--max-steps", help="Override inferred max_steps."),
    scoring_source: str | None = typer.Option(
        None,
        "--scoring-source",
        help="Override inferred scoring source: 'terminal' or 'episode_reward'.",
    ),
    benchmark_kind: str | None = typer.Option(
        None, "--kind", help="Hint for shape inference (e.g. qa_mcq, interactive_env)."
    ),
    domain_json: Path | None = typer.Option(
        None,
        "--from-json",
        exists=True,
        readable=True,
        help="Send this JSON file as the request body, skipping inference.",
    ),
    base_url: str | None = BaseUrlOpt,
    skip_validation: bool = typer.Option(
        False, "--skip-validation", help="Skip the local pre-flight validation."
    ),
) -> None:
    """Register (or upsert as draft) a domain via POST /v1/domains."""
    if domain_json:
        body: dict[str, Any] = json.loads(domain_json.read_text(encoding="utf-8"))
    else:
        src: ScoringSource | None = None
        if scoring_source in ("terminal", "episode_reward"):
            src = scoring_source  # type: ignore[assignment]
        elif scoring_source not in (None, ""):
            _die("--scoring-source must be 'terminal' or 'episode_reward'")
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

    if not skip_validation:
        v = validation.validate_benchmark_config(body)
        if not v.get("ok"):
            err_console.print("[red]validation failed[/red] — payload NOT sent.")
            _print_json(v)
            raise typer.Exit(1)

    async def _go() -> dict[str, Any]:
        c = _client(base_url)
        try:
            return await c.upsert_domain(body)
        finally:
            await c.aclose()

    try:
        created = _run_async(_go())
    except httpx.HTTPStatusError as e:
        _print_json(_http_error_payload(e))
        raise typer.Exit(1) from e
    _print_json(created)


@app.command("publish")
def cmd_publish(
    benchmark_id: str = typer.Argument(..., help="Domain id to publish."),
    base_url: str | None = BaseUrlOpt,
) -> None:
    """Publish a domain (POST /v1/domains/{id}/publish)."""

    async def _go() -> dict[str, Any]:
        c = _client(base_url)
        try:
            return await c.publish_domain(benchmark_id)
        finally:
            await c.aclose()

    try:
        domain = _run_async(_go())
    except httpx.HTTPStatusError as e:
        _print_json(_http_error_payload(e))
        raise typer.Exit(1) from e
    arts = compile_benchmark_artifacts(domain)
    _print_json(
        {
            "domain": domain,
            "artifact_digests": {name: sha256_digest(content) for name, content in arts.items()},
        }
    )


@app.command("get")
def cmd_get(
    benchmark_id: str = typer.Argument(..., help="Domain id to fetch."),
    artifacts: bool = typer.Option(
        False, "--artifacts", help="Include synthesized contract/eval_profile/dataset_lock."
    ),
    base_url: str | None = BaseUrlOpt,
) -> None:
    """Fetch a domain (GET /v1/domains/{id})."""

    async def _go() -> dict[str, Any]:
        c = _client(base_url)
        try:
            return await c.get_domain(benchmark_id)
        finally:
            await c.aclose()

    try:
        domain = _run_async(_go())
    except httpx.HTTPStatusError as e:
        _print_json(_http_error_payload(e))
        raise typer.Exit(1) from e
    if artifacts:
        arts = compile_benchmark_artifacts(domain)
        _print_json(
            {
                "domain": domain,
                "artifacts": arts,
                "artifact_digests": {n: sha256_digest(c) for n, c in arts.items()},
            }
        )
    else:
        _print_json(domain)


@app.command("list")
def cmd_list(
    status: str = typer.Option("all", "--status", help="One of: all, published, draft."),
    plain: bool = typer.Option(False, "--json", help="Output raw JSON instead of a table."),
    base_url: str | None = BaseUrlOpt,
) -> None:
    """List domains (GET /v1/domains)."""
    if status not in ("all", "published", "draft"):
        _die("--status must be one of: all, published, draft")

    async def _go() -> list[dict[str, Any]]:
        c = _client(base_url)
        try:
            if status == "published":
                return await c.list_domains(published_only=True)
            return await c.list_domains(published_only=None)
        finally:
            await c.aclose()

    try:
        items = _run_async(_go())
    except httpx.HTTPStatusError as e:
        _print_json(_http_error_payload(e))
        raise typer.Exit(1) from e
    if status == "draft":
        items = [d for d in items if d.get("status") == "draft"]

    if plain or not sys.stdout.isatty():
        _print_json({"benchmarks": items, "count": len(items)})
        return

    table = Table(title=f"benchmarks ({len(items)} total, status={status})")
    table.add_column("id", style="cyan")
    table.add_column("name")
    table.add_column("status", style="green")
    table.add_column("owner")
    for d in items:
        table.add_row(
            str(d.get("id", "")),
            str(d.get("name", "")),
            str(d.get("status", "")),
            str(d.get("owner_id", "")),
        )
    console.print(table)


# ── eval execution ──────────────────────────────────────────────────────


@eval_app.command("test")
def cmd_eval_test(
    domain_id: str = typer.Option(..., "--domain-id", help="Target domain id."),
    binding_vow_version: str = typer.Option(..., "--vow-version", help="Binding vow version."),
    model: str = typer.Option(..., "--model", help="Model identifier (e.g. openai/gpt-4o-mini)."),
    env_url: str | None = typer.Option(None, "--env-url", help="Override env URL."),
    seed: int | None = typer.Option(None, "--seed", help="Episode seed."),
    temperature: float = typer.Option(0.0, "--temperature"),
    max_tokens: int = typer.Option(4096, "--max-tokens"),
    base_url: str | None = BaseUrlOpt,
) -> None:
    """One-off test episode (POST /v1/test/episode)."""
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

    async def _go() -> dict[str, Any]:
        c = _client(base_url)
        try:
            return await c.test_episode(body)
        finally:
            await c.aclose()

    try:
        _print_json(_run_async(_go()))
    except httpx.HTTPStatusError as e:
        _print_json(_http_error_payload(e))
        raise typer.Exit(1) from e


@eval_app.command("run")
def cmd_eval_run(
    domain_id: str = typer.Option(..., "--domain-id"),
    binding_vow_version: str = typer.Option(..., "--vow-version"),
    model: str = typer.Option(..., "--model"),
    num_episodes: int = typer.Option(1, "--num-episodes"),
    seed_set: str | None = typer.Option(
        None, "--seed-set", help="JSON array of seeds, e.g. '[1,2,3]'."
    ),
    temperature: float = typer.Option(0.0, "--temperature"),
    max_tokens: int = typer.Option(4096, "--max-tokens"),
    max_parallel: int = typer.Option(1, "--max-parallel"),
    require_published: bool = typer.Option(
        True,
        "--require-published/--allow-draft",
        help="Reject runs against non-published domains by default.",
    ),
    base_url: str | None = BaseUrlOpt,
) -> None:
    """Full run with scoring aggregation (POST /v1/runs)."""
    seeds: list[int] | None = None
    if seed_set:
        try:
            seeds = json.loads(seed_set)
            if not isinstance(seeds, list):
                raise ValueError
        except Exception:
            _die("--seed-set must be a JSON array of integers, e.g. '[1,2,3]'")

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

    async def _go() -> dict[str, Any]:
        c = _client(base_url)
        try:
            if require_published:
                dom = await c.get_domain(domain_id)
                if dom.get("status") != "published":
                    return {
                        "error": "domain_not_published",
                        "status": dom.get("status"),
                        "hint": "Use --allow-draft to bypass.",
                    }
            return await c.create_run(body)
        finally:
            await c.aclose()

    try:
        result = _run_async(_go())
    except httpx.HTTPStatusError as e:
        _print_json(_http_error_payload(e))
        raise typer.Exit(1) from e
    _print_json(result)
    if result.get("error") == "domain_not_published":
        raise typer.Exit(1)


# ── run inspection ──────────────────────────────────────────────────────


@run_app.command("get")
def cmd_run_get(
    run_id: str = typer.Argument(...),
    base_url: str | None = BaseUrlOpt,
) -> None:
    """Run status + aggregate scores (GET /v1/runs/{id})."""

    async def _go() -> dict[str, Any]:
        c = _client(base_url)
        try:
            run = await c.get_run(run_id)
            episodes = await c.list_episodes(run_id)
            return {"run": run, "episodes": episodes, "aggregate_scores": run.get("scores", {})}
        finally:
            await c.aclose()

    try:
        _print_json(_run_async(_go()))
    except httpx.HTTPStatusError as e:
        _print_json(_http_error_payload(e))
        raise typer.Exit(1) from e


@run_app.command("episodes")
def cmd_run_episodes(
    run_id: str = typer.Argument(...),
    include_traces: bool = typer.Option(False, "--traces", help="Include per-episode traces."),
    base_url: str | None = BaseUrlOpt,
) -> None:
    """List episodes for a run (GET /v1/runs/{id}/episodes)."""

    async def _go() -> dict[str, Any]:
        c = _client(base_url)
        try:
            episodes = await c.list_episodes(run_id)
            traces: dict[str, Any] = {}
            if include_traces:
                traces = await c.get_run_traces(run_id)
            return {"run_id": run_id, "episodes": episodes, "traces_by_episode": traces}
        finally:
            await c.aclose()

    try:
        _print_json(_run_async(_go()))
    except httpx.HTTPStatusError as e:
        _print_json(_http_error_payload(e))
        raise typer.Exit(1) from e


def main() -> None:
    app()


if __name__ == "__main__":
    main()
