"""Unified bench CLI: auth, teams, env, register wrappers."""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx
from bench_common.auth.credentials import clear_credentials, load_credentials, save_credentials
from bench_common.auth.session import get_bench_session
from bench_common.auth.swecc_server import fetch_jwt, login


def _default_bench_url() -> str:
    return os.environ.get("SWECC_BENCH_URL", "https://api.swecc.org/bench").rstrip("/")


def _default_server_url() -> str:
    return os.environ.get("SWECC_SERVER_URL", "https://api.swecc.org").rstrip("/")


def _bench_url(args: argparse.Namespace) -> str:
    creds = load_credentials() or {}
    return (args.bench_url or creds.get("bench_url") or _default_bench_url()).rstrip("/")


def _active_team_id(args: argparse.Namespace) -> str | None:
    if getattr(args, "solo", False):
        return None
    if getattr(args, "team", None):
        return args.team
    creds = load_credentials() or {}
    return creds.get("active_team_id")


def _cmd_auth_login(args: argparse.Namespace) -> None:
    server = (args.server_url or _default_server_url()).rstrip("/")
    with httpx.Client(base_url=server, follow_redirects=True) as client:
        login(client, server, args.username, args.password)
        token = fetch_jwt(client, server)
    save_credentials(
        {
            "mode": "member",
            "token": token,
            "server_url": server,
            "bench_url": _bench_url(args),
        }
    )
    print("Logged in. Member JWT saved.")


def _cmd_auth_guest(args: argparse.Namespace) -> None:
    bench = _bench_url(args)
    r = httpx.post(f"{bench}/v1/auth/guest", timeout=30.0)
    r.raise_for_status()
    data = r.json()
    save_credentials({"mode": "guest", "token": data["guest_token"], "bench_url": bench})
    print(f"Guest session created (expires {data['expires_at']}).")


def _cmd_auth_whoami(args: argparse.Namespace) -> None:
    with get_bench_session(bench_url=_bench_url(args)) as session:
        r = session.client.get("/v1/me")
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def _cmd_auth_logout(_args: argparse.Namespace) -> None:
    clear_credentials()
    print("Credentials cleared.")


def _cmd_auth_token(_args: argparse.Namespace) -> None:
    """Print member JWT for curl/scripts (run auth login first)."""
    creds = load_credentials()
    if not creds or creds.get("mode") != "member" or not creds.get("token"):
        print("No member session. Run: bench auth login --username USER --password PASS", file=sys.stderr)
        sys.exit(1)
    print(creds["token"])


def _require_member_session(args: argparse.Namespace):
    creds = load_credentials()
    if creds and creds.get("mode") == "guest":
        print("This command requires a member account. Run: bench auth login", file=sys.stderr)
        sys.exit(1)
    return get_bench_session(bench_url=_bench_url(args))


def _cmd_team_create(args: argparse.Namespace) -> None:
    with _require_member_session(args) as session:
        r = session.client.post("/v1/teams", json={"name": args.name})
        r.raise_for_status()
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

    with get_bench_session(bench_url=_bench_url(args)) as session:
        r = session.client.post("/v1/runs", json=payload)
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


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
    parser = argparse.ArgumentParser(prog="bench", description="SWECC Bench CLI")
    parser.add_argument(
        "--bench-url",
        default=None,
        help=f"bench-api base URL (default: {_default_bench_url()} or saved credentials)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth")
    auth_sub = auth.add_subparsers(dest="auth_cmd", required=True)
    p = auth_sub.add_parser("login")
    p.add_argument(
        "--server-url",
        default=None,
        help=f"swecc-server base URL (default: {_default_server_url()} or SWECC_SERVER_URL)",
    )
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)
    p.set_defaults(func=_cmd_auth_login)
    p = auth_sub.add_parser("token")
    p.help = "Print saved member JWT (for curl); login first"
    p.set_defaults(func=_cmd_auth_token)
    p = auth_sub.add_parser("guest")
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
    p.set_defaults(func=_cmd_run_create)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
