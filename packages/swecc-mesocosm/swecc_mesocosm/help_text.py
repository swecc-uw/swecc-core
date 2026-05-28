"""Unified top-level help for mesocosm (Typer API client + bench_common env author)."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from swecc_mesocosm import __version__


def _command_table(rows: list[tuple[str, str]]) -> Table:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("command", style="cyan", no_wrap=True)
    table.add_column("help", style="")
    for name, help_text in rows:
        table.add_row(name, help_text)
    return table


def print_root_help(*, console: Console | None = None) -> None:
    """Print full command tree (used for ``mesocosm --help``)."""
    c = console or Console()
    c.print(
        Panel(
            "CLI for SWECC BenchAnything / Mesocosm — platform API, local Ollama runs, "
            "and env authoring.",
            title=f"mesocosm {__version__}",
            border_style="blue",
        )
    )
    c.print("\n[bold]Usage:[/bold] mesocosm [OPTIONS] COMMAND [ARGS]...\n")

    c.print("[bold]Options[/bold]")
    c.print("  -V, --version  Show version and exit.")
    c.print("  --help         Show this message and exit.\n")

    sections: list[tuple[str, list[tuple[str, str]]]] = [
        (
            "Auth & session (swecc-server + bench-api)",
            [
                (
                    "auth login",
                    "Log in (prompts for username and password)",
                ),
                ("auth token", "Print saved JWT (for curl/scripts)"),
                ("auth guest", "Create a guest session (bench-api only)"),
                ("auth whoami", "Show current principal (GET /v1/me)"),
                ("auth logout", "Clear saved credentials"),
            ],
        ),
        (
            "Teams",
            [
                ("team create", "Create a team (--use to set active)"),
                ("team join CODE", "Join with invite code"),
                ("team list", "List your teams"),
                ("team show TEAM_ID", "Team details"),
                ("team use TEAM_ID", "Set active team for runs/env"),
                ("team clear", "Clear active team (solo)"),
                ("team runs TEAM_ID", "List runs for a team"),
                ("team code show|regenerate", "View or rotate join code"),
                ("team members remove", "Remove a member (owner)"),
                ("team transfer", "Transfer ownership"),
                ("team leave|delete", "Leave or delete a team"),
            ],
        ),
        (
            "Local env authoring",
            [
                ("init", "Scaffold files/ (env + bench), showcase/, LOCAL_DEV.md"),
                ("run local", "Ollama bench; starts files/adapter.py (no API)"),
            ],
        ),
        (
            "Platform env & runs",
            [
                ("env submit", "Submit GitHub repo as developer environment"),
                ("env list", "List your environments"),
                ("run create", "Start a bench run on the platform"),
                ("run export RUN_ID", "Download run JSON for showcase/replay"),
            ],
        ),
        (
            "Connectivity & validation",
            [
                ("doctor", "Check bench-api URL and /bench prefix"),
                ("doctor --local", "Check env adapter (:8765) for run local"),
                ("validate FILE", "Validate domain JSON against policy (pre-submit check)"),
                (
                    "register domain.py",
                    "(legacy) Repos with DOMAIN_CONFIG in domain.py "
                    "(--auto-id, --publish); use env submit for new repos",
                ),
            ],
        ),
        (
            "Evaluations (bench-api)",
            [
                ("eval test", "Run a single dev test episode"),
                ("eval run", "Run a private multi-episode eval"),
            ],
        ),
        (
            "Run inspection (bench-api)",
            [
                ("run get RUN_ID", "Fetch run status and scores"),
                ("run episodes RUN_ID", "List episodes (--traces optional)"),
            ],
        ),
    ]

    for title, rows in sections:
        c.print(f"[bold]{title}[/bold]")
        c.print(_command_table(rows))
        c.print()

    c.print(
        "[dim]Tip: mesocosm COMMAND --help for subcommand details. "
        "Remote defaults: api.swecc.org (+ /bench). Local: MESOCOSM_LOCAL=1 or doctor --local.[/dim]"
    )


def print_run_help(*, console: Console | None = None) -> None:
    """Print help for ``mesocosm run`` (platform + inspection subcommands)."""
    c = console or Console()
    c.print("\n[bold]Usage:[/bold] mesocosm run COMMAND [ARGS]...\n")
    c.print("[bold]Platform & local (env author)[/bold]")
    c.print(
        _command_table(
            [
                ("create", "Start a platform bench run (requires auth login)"),
                ("local", "Local Ollama loop via benchanything.json"),
                ("export RUN_ID", "Export run + traces for showcase"),
            ]
        )
    )
    c.print()
    c.print("[bold]Inspection (bench-api)[/bold]")
    c.print(
        _command_table(
            [
                ("get RUN_ID", "Fetch run status and aggregate scores"),
                ("episodes RUN_ID", "List episodes (--traces to include traces)"),
            ]
        )
    )
    c.print()
