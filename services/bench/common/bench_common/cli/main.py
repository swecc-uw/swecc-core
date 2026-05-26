"""Unified bench CLI: auth, teams, env, register wrappers."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import warnings

import httpx
from bench_common.auth.credentials import clear_credentials, load_credentials, save_credentials
from bench_common.auth.session import get_bench_session
from bench_common.auth.swecc_server import fetch_jwt, login
from bench_common.cli.urls import (
    default_bench_api_url,
    default_server_url,
    guest_bench_api_url,
    is_stale_local_bench_url,
    member_bench_api_url,
    whoami_bench_api_url,
)


def _default_bench_url() -> str:
    return default_bench_api_url()


def _default_server_url() -> str:
    return default_server_url()


def _bench_url(args: argparse.Namespace) -> str:
    creds = load_credentials() or {}
    return member_bench_api_url(
        server_url=creds.get("server_url"),
        cli_bench_url=args.bench_url,
        creds=creds,
    )


def _bench_url_for_guest(args: argparse.Namespace) -> str:
    """Guest creation URL: CLI flag or explicit env only (never saved creds or MESOCOSM_LOCAL)."""
    if args.bench_url:
        return args.bench_url.rstrip("/")
    return guest_bench_api_url()


def _format_http_error(response: httpx.Response) -> str:
    """Best-effort message for bench-api HTTP errors (includes JSON detail when present)."""
    try:
        body = response.json()
        detail = body.get("detail")
        if detail is not None:
            if not isinstance(detail, str):
                detail = json.dumps(detail)
            return f"HTTP {response.status_code} for {response.request.method} {response.url}: {detail}"
    except (json.JSONDecodeError, ValueError):
        pass
    return f"HTTP {response.status_code} for {response.request.method} {response.url}"


def _guest_connect_error_message(bench: str, exc: httpx.ConnectError) -> str:
    return (
        f"Could not connect to bench-api at {bench}\n"
        f"  ({exc})\n"
        "For production guest auth:\n"
        "  unset MESOCOSM_LOCAL\n"
        "  mesocosm auth guest\n"
        "Or set the API explicitly:\n"
        "  export SWECC_BENCH_URL=https://api.swecc.org/bench\n"
        "  mesocosm auth guest\n"
        "For local docker:\n"
        "  docker compose up bench-api\n"
        "  mesocosm auth guest --bench-url http://127.0.0.1:8010"
    )


def _whoami_connect_error_message(
    bench: str, exc: httpx.ConnectError, creds: dict | None
) -> str:
    creds = creds or {}
    lines = [
        f"Could not connect to bench-api at {bench}\n",
        f"  ({exc})",
    ]
    if creds.get("mode") == "guest":
        lines.extend(
            [
                "For production guest whoami:",
                "  unset MESOCOSM_LOCAL",
                "  mesocosm auth guest",
                "Or set the API explicitly:",
                "  export SWECC_BENCH_URL=https://api.swecc.org/bench",
                "  mesocosm auth whoami",
            ]
        )
    else:
        saved = creds.get("bench_url") or ""
        server = creds.get("server_url") or ""
        if server and saved and is_stale_local_bench_url(saved, server_url=server):
            lines.append(
                f"Credentials have stale bench_url ({saved}) for server {server}."
            )
            lines.append(
                f"  mesocosm auth login --server-url {server} --username ..."
            )
        lines.extend(
            [
                "For production member whoami:",
                "  unset MESOCOSM_LOCAL",
                "  mesocosm auth login --server-url https://api.swecc.org ...",
                "Or fix ~/.config/swecc/bench_credentials.json:",
                '  "bench_url": "https://api.swecc.org/bench"',
                "Or: mesocosm auth logout && mesocosm auth login ...",
            ]
        )
    lines.extend(
        [
            "For local docker:",
            "  docker compose up bench-api",
            "  mesocosm auth whoami --bench-url http://127.0.0.1:8010",
        ]
    )
    return "\n".join(lines)


def _active_team_id(args: argparse.Namespace) -> str | None:
    if getattr(args, "solo", False):
        return None
    if getattr(args, "team", None):
        return args.team
    creds = load_credentials() or {}
    return creds.get("active_team_id")


def _resolve_login_password(args: argparse.Namespace) -> str:
    if args.password is not None:
        warnings.warn(
            "--password on the command line is deprecated; omit it to be prompted securely.",
            DeprecationWarning,
            stacklevel=2,
        )
        return args.password
    return getpass.getpass("Password: ")


def _cmd_auth_login(args: argparse.Namespace) -> None:
    password = _resolve_login_password(args)
    server = (args.server_url or _default_server_url()).rstrip("/")
    try:
        with httpx.Client(base_url=server, follow_redirects=True) as client:
            login(client, server, args.username, password)
            token = fetch_jwt(client, server)
    except httpx.HTTPStatusError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    save_credentials(
        {
            "mode": "member",
            "token": token,
            "server_url": server,
            "bench_url": member_bench_api_url(
                server_url=server,
                cli_bench_url=args.bench_url,
            ),
        }
    )
    print("Logged in. Member JWT saved.")


def _cmd_auth_guest(args: argparse.Namespace) -> None:
    bench = _bench_url_for_guest(args)
    try:
        r = httpx.post(f"{bench}/v1/auth/guest", timeout=30.0)
        r.raise_for_status()
    except httpx.ConnectError as exc:
        print(_guest_connect_error_message(bench, exc), file=sys.stderr)
        sys.exit(1)
    data = r.json()
    save_credentials({"mode": "guest", "token": data["guest_token"], "bench_url": bench})
    print(f"Guest session created (expires {data['expires_at']}).")


def _cmd_auth_whoami(args: argparse.Namespace) -> None:
    creds = load_credentials() or {}
    bench = whoami_bench_api_url(cli_bench_url=args.bench_url, creds=creds)
    try:
        with get_bench_session(bench_url=bench) as session:
            r = session.client.get("/v1/me")
            r.raise_for_status()
            data = r.json()
    except httpx.ConnectError as exc:
        print(_whoami_connect_error_message(bench, exc, creds), file=sys.stderr)
        sys.exit(1)

    if data.get("type") == "anonymous" and creds.get("mode") == "guest":
        print(
            "Guest token was not recognized at this bench-api URL.\n"
            f"  Tried: {bench}\n"
            "  mesocosm auth guest   # refresh credentials\n"
            "  Or: export SWECC_BENCH_URL=https://api.swecc.org/bench",
            file=sys.stderr,
        )
        sys.exit(1)

    print(json.dumps(data, indent=2))


def _cmd_auth_logout(_args: argparse.Namespace) -> None:
    clear_credentials()
    print("Credentials cleared.")


def _cmd_auth_token(_args: argparse.Namespace) -> None:
    """Print member JWT for curl/scripts (run auth login first)."""
    creds = load_credentials()
    if not creds or creds.get("mode") != "member" or not creds.get("token"):
        print(
            "No member session. Run: mesocosm auth login --username USER",
            file=sys.stderr,
        )
        sys.exit(1)
    print(creds["token"])


def _require_member_session(args: argparse.Namespace):
    creds = load_credentials()
    if creds and creds.get("mode") == "guest":
        print("This command requires a member account. Run: mesocosm auth login", file=sys.stderr)
        sys.exit(1)
    return get_bench_session(bench_url=_bench_url(args))


def _cmd_team_create(args: argparse.Namespace) -> None:
    with _require_member_session(args) as session:
        r = session.client.post("/v1/teams", json={"name": args.name})
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            print(_format_http_error(exc.response), file=sys.stderr)
            sys.exit(1)
        data = r.json()
        print(f"team_id={data['team_id']}")
        print(
            f"join_code={data['join_code']}  ({data['member_count']}/{data['max_members']} members)"
        )
        if args.use:
            creds = load_credentials() or {}
            creds["active_team_id"] = data["team_id"]
            save_credentials(creds)


def _cmd_team_join(args: argparse.Namespace) -> None:
    with _require_member_session(args) as session:
        r = session.client.post("/v1/teams/join", json={"code": args.code.upper()})
        r.raise_for_status()
        data = r.json()
        print(
            f"Joined {data['name']} ({data['member_count']}/{data['max_members']}) team_id={data['team_id']}"
        )


def _cmd_team_list(args: argparse.Namespace) -> None:
    with _require_member_session(args) as session:
        r = session.client.get("/v1/teams")
        r.raise_for_status()
        for t in r.json():
            code = f"  code={t['join_code']}" if t.get("join_code") else ""
            print(
                f"{t['team_id']}  {t['name']}  ({t['member_count']}/{t['max_members']})  {t['role']}{code}"
            )


def _cmd_team_show(args: argparse.Namespace) -> None:
    with _require_member_session(args) as session:
        r = session.client.get(f"/v1/teams/{args.team_id}")
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def _cmd_team_delete(args: argparse.Namespace) -> None:
    with _require_member_session(args) as session:
        r = session.client.delete(f"/v1/teams/{args.team_id}")
        r.raise_for_status()
        print("Team deleted.")


def _cmd_team_leave(args: argparse.Namespace) -> None:
    with _require_member_session(args) as session:
        r = session.client.delete(f"/v1/teams/{args.team_id}/members/me")
        r.raise_for_status()
        print("Left team.")


def _cmd_team_code_show(args: argparse.Namespace) -> None:
    _cmd_team_show(args)


def _cmd_team_code_regenerate(args: argparse.Namespace) -> None:
    with _require_member_session(args) as session:
        r = session.client.post(f"/v1/teams/{args.team_id}/join-code/regenerate")
        r.raise_for_status()
        print(f"join_code={r.json()['join_code']}")


def _cmd_team_members_remove(args: argparse.Namespace) -> None:
    with _require_member_session(args) as session:
        r = session.client.delete(f"/v1/teams/{args.team_id}/members/{args.user_id}")
        r.raise_for_status()
        print("Member removed.")


def _cmd_team_transfer(args: argparse.Namespace) -> None:
    with _require_member_session(args) as session:
        r = session.client.post(
            f"/v1/teams/{args.team_id}/transfer",
            json={"new_owner_user_id": args.user_id},
        )
        r.raise_for_status()
        print("Ownership transferred.")


def _cmd_team_use(args: argparse.Namespace) -> None:
    creds = load_credentials() or {}
    creds["active_team_id"] = args.team_id
    creds.setdefault("bench_url", _bench_url(args))
    save_credentials(creds)
    print(f"Active team set to {args.team_id}")


def _cmd_team_clear(_args: argparse.Namespace) -> None:
    creds = load_credentials() or {}
    creds.pop("active_team_id", None)
    save_credentials(creds)
    print("Active team cleared (solo default).")


def _cmd_team_runs(args: argparse.Namespace) -> None:
    with _require_member_session(args) as session:
        r = session.client.get(f"/v1/teams/{args.team_id}/runs")
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def _cmd_env_submit(args: argparse.Namespace) -> None:
    team_id = _active_team_id(args)
    payload = {
        "name": args.name,
        "description": args.description or "",
        "github_url": args.github_url,
    }
    if team_id:
        payload["team_id"] = team_id
    with _require_member_session(args) as session:
        r = session.client.post("/v1/developer/environments", json=payload)
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def _cmd_env_list(args: argparse.Namespace) -> None:
    team_id = _active_team_id(args)
    params = {}
    if team_id:
        params = {"scope": "team", "team_id": team_id}
    with _require_member_session(args) as session:
        r = session.client.get("/v1/developer/environments", params=params)
        r.raise_for_status()
        for env in r.json():
            print(f"{env['id']}  {env['status']}  {env.get('scope', 'solo')}  {env['name']}")


def _cmd_run_create(args: argparse.Namespace) -> None:
    team_id = _active_team_id(args)
    payload: dict = {
        "domain_id": args.domain,
        "binding_vow_version": args.vow_version,
        "agent_config": {
            "model": args.model,
            "system_prompt": args.system_prompt,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
        },
        "num_episodes": args.episodes,
        "max_parallel": args.parallel,
    }
    if team_id:
        payload["team_id"] = team_id
    if args.visibility:
        payload["visibility"] = args.visibility
    if getattr(args, "env_id", None):
        payload["env_id"] = args.env_id

    with get_bench_session(bench_url=_bench_url(args)) as session:
        r = session.client.post("/v1/runs", json=payload)
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def _cmd_run_local(args: argparse.Namespace) -> None:
    """Run episodes locally via Ollama + benchanything.json (no platform submit)."""
    import asyncio
    from pathlib import Path

    from bench_common.env_sdk.manifest import domain_config_from_manifest
    from bench_common.inference.bench import bench

    model = args.model or "ollama/llama3.2"
    if not model.startswith("ollama/"):
        print(
            "mesocosm run local only supports Ollama models (e.g. ollama/llama3.2).\n"
            "Install Ollama, run `ollama pull llama3.2`, then retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    manifest_path = Path(args.manifest).resolve()
    domain = domain_config_from_manifest(
        manifest_path,
        domain_id=args.domain_id,
        env_url=args.env_url,
    )
    result = asyncio.run(
        bench(
            model=model,
            domain_id=domain.id,
            env_url=args.env_url,
            num_episodes=args.episodes,
            seed_set=args.seeds,
            system_prompt=args.system_prompt,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            max_parallel=args.parallel,
            quiet=args.quiet,
            domain=domain,
            allow_any_model=True,
        )
    )
    print(result)


def _cmd_run_export(args: argparse.Namespace) -> None:
    out_path = args.output
    with get_bench_session(bench_url=_bench_url(args)) as session:
        r = session.client.get(f"/v1/runs/{args.run_id}/export")
        r.raise_for_status()
        data = r.json()
    text = json.dumps(data, indent=2)
    if out_path:
        from pathlib import Path

        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {path}")
    else:
        print(text)


def _cmd_init(args: argparse.Namespace) -> None:
    from importlib import resources
    from pathlib import Path

    dest = Path(args.dir or ".").resolve()
    pkg = resources.files("bench_common.cli.templates")
    files = {
        "benchanything.json": "benchanything.json",
        "adapter.py": "adapter.py",
        "env.py": "env.py",
        "requirements.txt": "requirements.txt",
        "LOCAL_DEV.md": "LOCAL_DEV.md",
    }
    for src_name, out_name in files.items():
        target = dest / out_name
        if target.exists() and not args.force:
            print(f"skip (exists): {target}")
            continue
        target.write_text(pkg.joinpath(src_name).read_text(encoding="utf-8"), encoding="utf-8")
        print(f"wrote {target}")

    showcase = dest / "showcase"
    showcase.mkdir(parents=True, exist_ok=True)
    for src, out in (
        ("showcase_README.md", "README.md"),
        ("replay.example.json", "replay.example.json"),
    ):
        target = showcase / out
        if target.exists() and not args.force:
            print(f"skip (exists): {target}")
            continue
        target.write_text(pkg.joinpath(src).read_text(encoding="utf-8"), encoding="utf-8")
        print(f"wrote {target}")

    print(
        "\nNext:\n"
        "  1. pip install swecc-mesocosm  (CLI + adapter deps; not requirements.txt)\n"
        "  2. Edit env.py + benchanything.json\n"
        "  3. Local Ollama loop (see LOCAL_DEV.md):\n"
        "       ollama pull llama3.2 && python adapter.py\n"
        "       mesocosm run local\n"
        "  4. When ready: mesocosm env submit --github-url ...\n"
        "  (requirements.txt: optional extras for your env — see file header)"
    )


def _cmd_register(args: argparse.Namespace) -> None:
    from pathlib import Path

    from bench_common.env_sdk.register import _load_domain_config
    from bench_common.env_sdk.registration import publish_domain, register_domain

    cfg = _load_domain_config(args.domain_file)
    if args.auto_id:
        cfg = cfg.model_copy(update={"id": Path(args.domain_file).parent.name})
    api = _bench_url(args)
    register_domain(cfg, api_url=api)
    if args.publish:
        publish_domain(cfg.id, api_url=api)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mesocosm", description="SWECC Bench / Mesocosm CLI")
    parser.add_argument(
        "--bench-url",
        default=None,
        help=f"bench-api base URL (default: {_default_bench_url()} or saved credentials)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth")
    auth_sub = auth.add_subparsers(dest="auth_cmd", required=True)
    p = auth_sub.add_parser(
        "login",
        description=(
            "Log in with swecc-server (username + password). Passwords are verified "
            "server-side over HTTPS; the CLI never hashes them locally. Omit --password "
            "to be prompted securely (not stored in shell history)."
        ),
    )
    p.add_argument(
        "--server-url",
        default=None,
        help=f"swecc-server base URL (default: {_default_server_url()} or SWECC_SERVER_URL)",
    )
    p.add_argument("--username", required=True)
    p.add_argument(
        "--password",
        default=None,
        help="password (deprecated: visible in shell history; omit to prompt)",
    )
    p.set_defaults(func=_cmd_auth_login)
    p = auth_sub.add_parser("token")
    p.help = "Print saved member JWT (for curl); login first"
    p.set_defaults(func=_cmd_auth_token)
    p = auth_sub.add_parser(
        "guest",
        help="Create a guest session (defaults to production bench-api)",
    )
    p.add_argument(
        "--bench-url",
        default=None,
        dest="bench_url",
        metavar="URL",
        help=(
            "bench-api base URL (default: https://api.swecc.org/bench; "
            "ignores saved credentials and MESOCOSM_LOCAL)"
        ),
    )
    p.set_defaults(func=_cmd_auth_guest)
    p = auth_sub.add_parser("whoami")
    p.set_defaults(func=_cmd_auth_whoami)
    p = auth_sub.add_parser("logout")
    p.set_defaults(func=_cmd_auth_logout)

    team = sub.add_parser("team")
    team_sub = team.add_subparsers(dest="team_cmd", required=True)
    p = team_sub.add_parser("create")
    p.add_argument("--name", required=True)
    p.add_argument("--use", action="store_true", help="Set as active team in credentials")
    p.set_defaults(func=_cmd_team_create)
    p = team_sub.add_parser("join")
    p.add_argument("code")
    p.set_defaults(func=_cmd_team_join)
    p = team_sub.add_parser("list")
    p.set_defaults(func=_cmd_team_list)
    p = team_sub.add_parser("show")
    p.add_argument("team_id")
    p.set_defaults(func=_cmd_team_show)
    p = team_sub.add_parser("delete")
    p.add_argument("team_id")
    p.set_defaults(func=_cmd_team_delete)
    p = team_sub.add_parser("leave")
    p.add_argument("team_id")
    p.set_defaults(func=_cmd_team_leave)
    p = team_sub.add_parser("use")
    p.add_argument("team_id")
    p.set_defaults(func=_cmd_team_use)
    p = team_sub.add_parser("clear")
    p.set_defaults(func=_cmd_team_clear)
    p = team_sub.add_parser("runs")
    p.add_argument("team_id")
    p.set_defaults(func=_cmd_team_runs)
    code = team_sub.add_parser("code")
    code_sub = code.add_subparsers(dest="code_cmd", required=True)
    p = code_sub.add_parser("show")
    p.add_argument("team_id")
    p.set_defaults(func=_cmd_team_code_show)
    p = code_sub.add_parser("regenerate")
    p.add_argument("team_id")
    p.set_defaults(func=_cmd_team_code_regenerate)
    members = team_sub.add_parser("members")
    members_sub = members.add_subparsers(dest="members_cmd", required=True)
    p = members_sub.add_parser("remove")
    p.add_argument("team_id")
    p.add_argument("--user-id", type=int, required=True)
    p.set_defaults(func=_cmd_team_members_remove)
    p = team_sub.add_parser("transfer")
    p.add_argument("team_id")
    p.add_argument("--user-id", type=int, required=True)
    p.set_defaults(func=_cmd_team_transfer)

    env = sub.add_parser("env")
    env_sub = env.add_subparsers(dest="env_cmd", required=True)
    p = env_sub.add_parser("submit")
    p.add_argument("--name", required=True)
    p.add_argument("--github-url", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--team", default=None)
    p.add_argument("--solo", action="store_true")
    p.set_defaults(func=_cmd_env_submit)
    p = env_sub.add_parser("list")
    p.add_argument("--team", default=None)
    p.add_argument("--solo", action="store_true")
    p.set_defaults(func=_cmd_env_list)

    reg = sub.add_parser("register")
    reg.add_argument("domain_file")
    reg.add_argument("--auto-id", action="store_true")
    reg.add_argument("--publish", action="store_true")
    reg.set_defaults(func=_cmd_register)

    run_p = sub.add_parser("run")
    run_sub = run_p.add_subparsers(dest="run_cmd", required=True)
    p = run_sub.add_parser("create")
    p.add_argument("--domain", required=True)
    p.add_argument("--vow-version", required=True, help="Binding vow version string")
    p.add_argument("--model", required=True)
    p.add_argument("--episodes", type=int, default=1)
    p.add_argument("--parallel", type=int, default=1)
    p.add_argument("--system-prompt", default=None)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--team", default=None)
    p.add_argument("--solo", action="store_true")
    p.add_argument("--visibility", choices=["private", "gallery_public"], default=None)
    p.add_argument("--env-id", default=None, dest="env_id", help="Developer environment id")
    p.set_defaults(func=_cmd_run_create)
    p = run_sub.add_parser(
        "local",
        help="Bench via Ollama + benchanything.json (no API submit; see LOCAL_DEV.md)",
    )
    p.add_argument(
        "--manifest",
        default="benchanything.json",
        help="Path to benchanything.json (default: ./benchanything.json)",
    )
    p.add_argument(
        "--domain-id",
        default=None,
        help="Override domain id (default: manifest id or parent folder name)",
    )
    p.add_argument(
        "--model",
        default="ollama/llama3.2",
        help="Ollama model via LiteLLM (default: ollama/llama3.2)",
    )
    p.add_argument(
        "--env-url",
        default="http://localhost:8765",
        help="Adapter base URL (default: http://localhost:8765)",
    )
    p.add_argument("--episodes", type=int, default=5)
    p.add_argument("--seeds", type=int, nargs="+", default=None)
    p.add_argument("--system-prompt", default=None)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--parallel", type=int, default=1)
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=_cmd_run_local)
    p = run_sub.add_parser("export", help="Download run + traces + replay JSON for a showcase")
    p.add_argument("run_id")
    p.add_argument("-o", "--output", default=None, help="Write to file (default: stdout)")
    p.set_defaults(func=_cmd_run_export)

    init_p = sub.add_parser("init", help="Scaffold benchanything.json, adapter, env, showcase/")
    init_p.add_argument(
        "--dir",
        default=".",
        help="Target directory (default: current directory)",
    )
    init_p.add_argument("--force", action="store_true", help="Overwrite existing files")
    init_p.set_defaults(func=_cmd_init)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
