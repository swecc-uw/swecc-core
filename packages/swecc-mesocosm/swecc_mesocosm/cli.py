"""mesocosm CLI — talks to the bench API.

Run `mesocosm --help` for the command surface.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, cast

import httpx
import typer
from rich.console import Console
from rich.syntax import Syntax
from swecc_mesocosm import __version__, validation
from swecc_mesocosm.bench_dispatch import try_dispatch_bench
from swecc_mesocosm.client import BenchClient
from swecc_mesocosm.help_text import print_root_help, print_run_help
from swecc_mesocosm.settings import settings
from swecc_mesocosm.urls import default_bench_api_url, default_env_adapter_url, mesocosm_local_mode

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="CLI for SWECC BenchAnything / Mesocosm (see mesocosm --help for all commands).",
)
eval_app = typer.Typer(no_args_is_help=True, help="Run dev or private evaluations.")
run_app = typer.Typer(
    no_args_is_help=True,
    help="Platform runs, local Ollama, or inspect runs (mesocosm run --help).",
)
app.add_typer(eval_app, name="eval")
app.add_typer(run_app, name="run")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"mesocosm {__version__}")
        raise typer.Exit()


@app.callback()
def _main_options(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """mesocosm CLI options (root)."""


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


def _connection_error_payload(exc: httpx.RequestError) -> dict[str, Any]:
    return {
        "error": "connection_error",
        "kind": type(exc).__name__,
        "detail": str(exc),
        "url": str(exc.request.url) if exc.request is not None else None,
        "hint": "Is the bench-api server running and reachable at MESOCOSM_BASE_URL?",
    }


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


def _run_with_http_errors(coro: Any) -> Any:
    """Run an async API call; map httpx errors to clean JSON + exit 1."""
    try:
        return _run_async(coro)
    except httpx.HTTPStatusError as e:
        _print_json(_http_error_payload(e))
        raise typer.Exit(1) from e
    except httpx.RequestError as e:
        _print_json(_connection_error_payload(e))
        raise typer.Exit(1) from e


def _client(base_url: str | None) -> BenchClient:
    return BenchClient(base_url=base_url) if base_url else BenchClient()


_EPISODE_FAILURE_STATUSES = frozenset({"failed", "cancelled", "error"})
_RUN_FAILURE_STATUSES = frozenset({"failed", "cancelled", "error"})


def _effective_base_url(base_url: str | None) -> str:
    return (base_url or settings.base_url).rstrip("/")


async def _resolve_vow_version(
    client: BenchClient,
    domain_id: str,
    vow_version: str | None,
) -> str:
    if vow_version:
        return vow_version
    domain = await client.get_domain(domain_id)
    vow_raw = domain.get("binding_vow")
    if not isinstance(vow_raw, dict):
        _die(f"domain {domain_id!r} has no binding_vow; pass --vow-version explicitly")
    vow = cast(dict[str, Any], vow_raw)
    version = vow.get("version")
    if not version:
        _die(f"domain {domain_id!r} binding_vow has no version; pass --vow-version")
    return str(version)


def _exit_if_episode_failed(episode: dict[str, Any]) -> None:
    status = episode.get("status")
    if status in _EPISODE_FAILURE_STATUSES:
        err_console.print(
            f"[red]episode {status}[/red]"
            + (f": {episode.get('terminal_info')}" if episode.get("terminal_info") else "")
        )
        raise typer.Exit(1)


def _exit_if_run_unsuccessful(run: dict[str, Any], episodes: list[dict[str, Any]] | None) -> None:
    status = run.get("status")
    if status in _RUN_FAILURE_STATUSES:
        err_console.print(f"[red]run {status}[/red]")
        raise typer.Exit(1)
    if episodes:
        for ep in episodes:
            if ep.get("status") in _EPISODE_FAILURE_STATUSES:
                _exit_if_episode_failed(ep)


def _probe_url(url: str, *, timeout_s: float = 10.0) -> tuple[int | None, str | None]:
    try:
        response = httpx.get(url, timeout=timeout_s)
        return response.status_code, None
    except httpx.RequestError as exc:
        return None, str(exc)


BaseUrlOpt = typer.Option(
    None,
    "--base-url",
    envvar="MESOCOSM_BASE_URL",
    help=f"bench API URL (default: {settings.base_url}).",
)


# ── helpers (no API) ───────────────────────────────────────────────────


@app.command("validate")
def cmd_validate(
    payload: str = typer.Argument(
        ...,
        help="Path to a JSON file containing a POST /v1/domains body (use '-' for stdin).",
    ),
) -> None:
    """Validate a domain payload against the local policy/constraints.json."""
    if payload == "-":
        raw = sys.stdin.read()
    else:
        p = Path(payload)
        if not p.is_file():
            _die(f"no such file: {payload}")
        raw = p.read_text(encoding="utf-8")
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as e:
        _die(f"invalid JSON: {e}")
    result = validation.validate_benchmark_config(body)
    _print_json(result)
    raise typer.Exit(0 if result.get("ok") else 1)


@app.command("doctor")
def cmd_doctor(
    base_url: str | None = BaseUrlOpt,
    local: bool = typer.Option(
        False,
        "--local",
        help="Local dev: check env adapter (:8765) and bench-api (:8010); sets profile like MESOCOSM_LOCAL=1.",
    ),
) -> None:
    """Check bench-api reachability (and local env adapter when --local / MESOCOSM_LOCAL=1)."""
    local_profile = local or mesocosm_local_mode()
    base = _effective_base_url(base_url)
    health_url = f"{base}/health"
    openapi_url = f"{base}/openapi.json"

    health_code, health_err = _probe_url(health_url)
    openapi_code, openapi_err = _probe_url(openapi_url)

    issues: list[str] = []
    if health_err:
        issues.append(f"bench-api health unreachable: {health_err}")
        if "Connection refused" in health_err and not local_profile:
            issues.append(
                "hint: default is production — https://api.swecc.org/bench "
                "(use MESOCOSM_LOCAL=1 or mesocosm doctor --local for docker + adapter)"
            )
    elif health_code != 200:
        issues.append(f"bench-api GET /health returned {health_code}")

    if openapi_err:
        issues.append(f"bench-api openapi unreachable: {openapi_err}")
    elif openapi_code != 200:
        issues.append(f"bench-api GET /openapi.json returned {openapi_code}")
        if not base.rstrip("/").endswith("/bench"):
            issues.append(
                "hint: production bench-api is at https://api.swecc.org/bench — "
                "set MESOCOSM_BASE_URL to include the /bench prefix"
            )

    bench_ok = (
        health_err is None and health_code == 200 and openapi_err is None and openapi_code == 200
    )

    adapter_block: dict[str, Any] | None = None
    adapter_ok = False
    notes: list[str] = []
    if local_profile:
        adapter_base = default_env_adapter_url()
        adapter_health = f"{adapter_base}/health"
        adapter_code, adapter_err = _probe_url(adapter_health)
        adapter_block = {
            "url": adapter_health,
            "status_code": adapter_code,
            "error": adapter_err,
        }
        adapter_ok = adapter_err is None and adapter_code == 200
        if adapter_err:
            issues.append(
                f"env adapter unreachable: {adapter_err} "
                "(run: mesocosm run local, or python files/adapter.py)"
            )
        elif adapter_code != 200:
            issues.append(f"env adapter GET /health returned {adapter_code}")
        elif adapter_code == 200:
            notes.append(
                "env adapter health returned 200; if `python adapter.py` fails with "
                "address already in use, another process may be bound to the port"
            )
        if bench_ok and not adapter_ok:
            issues.append("bench-api ok; start env adapter for mesocosm run local")
        if adapter_ok and not bench_ok:
            issues.append(
                "env adapter ok; bench-api down — fine for `run local`, "
                "need docker compose for env submit / run create"
            )

    if local_profile:
        ok = adapter_ok
    else:
        ok = bench_ok

    payload: dict[str, Any] = {
        "ok": ok,
        "profile": "local" if local_profile else "remote",
        "base_url": base,
        "health": {
            "url": health_url,
            "status_code": health_code,
            "error": health_err,
        },
        "openapi": {
            "url": openapi_url,
            "status_code": openapi_code,
            "error": openapi_err,
        },
        "issues": issues,
    }
    if adapter_block is not None:
        payload["env_adapter"] = adapter_block
    if notes:
        payload["notes"] = notes
    _print_json(payload)
    raise typer.Exit(0 if ok else 1)


# ── eval execution ──────────────────────────────────────────────────────


@eval_app.command("test")
def cmd_eval_test(
    domain_id: str = typer.Option(..., "--domain-id", help="Target domain id."),
    binding_vow_version: str | None = typer.Option(
        None,
        "--vow-version",
        help="binding_vow.version (e.g. 1.0.0). Omit to read from the domain record.",
    ),
    model: str = typer.Option(..., "--model", help="Model identifier (e.g. openai/gpt-4o-mini)."),
    env_url: str | None = typer.Option(None, "--env-url", help="Override env URL."),
    seed: int | None = typer.Option(None, "--seed", help="Episode seed."),
    temperature: float = typer.Option(0.0, "--temperature"),
    max_tokens: int = typer.Option(4096, "--max-tokens"),
    base_url: str | None = BaseUrlOpt,
) -> None:
    """One-off test episode (POST /v1/test/episode)."""

    async def _go() -> dict[str, Any]:
        c = _client(base_url)
        try:
            vow_version = await _resolve_vow_version(c, domain_id, binding_vow_version)
            body: dict[str, Any] = {
                "domain_id": domain_id,
                "binding_vow_version": vow_version,
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
            return await c.test_episode(body)
        finally:
            await c.aclose()

    episode = _run_with_http_errors(_go())
    _print_json(episode)
    _exit_if_episode_failed(episode)


@eval_app.command("run")
def cmd_eval_run(
    domain_id: str = typer.Option(..., "--domain-id"),
    binding_vow_version: str | None = typer.Option(
        None,
        "--vow-version",
        help="binding_vow.version (e.g. 1.0.0). Omit to read from the domain record.",
    ),
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
            vow_version = await _resolve_vow_version(c, domain_id, binding_vow_version)
            body: dict[str, Any] = {
                "domain_id": domain_id,
                "binding_vow_version": vow_version,
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
            return await c.create_run(body)
        finally:
            await c.aclose()

    result = _run_with_http_errors(_go())
    _print_json(result)
    if result.get("error") == "domain_not_published":
        raise typer.Exit(1)
    if "episodes" in result:
        _exit_if_run_unsuccessful(result, result.get("episodes"))
    elif result.get("status") in _RUN_FAILURE_STATUSES:
        _exit_if_run_unsuccessful(result, None)


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
            return {
                "run": run,
                "episodes": episodes,
                "aggregate_scores": run.get("scores", {}),
            }
        finally:
            await c.aclose()

    _print_json(_run_with_http_errors(_go()))


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

    _print_json(_run_with_http_errors(_go()))


def main() -> None:
    argv = sys.argv[1:]
    if not argv or argv in (["--help"], ["-h"]):
        print_root_help()
        return
    if argv[:1] == ["run"] and (len(argv) == 1 or argv[1:] in (["--help"], ["-h"])):
        print_run_help()
        return
    if try_dispatch_bench(argv):
        return
    app()


if __name__ == "__main__":
    main()
