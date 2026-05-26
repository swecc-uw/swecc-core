"""Actionable hints when bench-api cannot reach expected Postgres tables."""


def init_db_hint(exc: Exception) -> str:
    hint = (
        "bench tables missing — run swecc-server `manage.py migrate` first, "
        "then restart bench-api."
    )
    err = str(exc).lower()
    if "bench_benchteam" in err or "bench_benchteammembership" in err:
        hint = (
            "bench team tables missing — redeploy/restart swecc-server so "
            "`manage.py migrate` applies bench.0002_auth_teams (teams API), "
            "then restart bench-api."
        )
    elif "tenant or user not found" in err or "password authentication failed" in err:
        hint = (
            "Postgres auth failed for bench-api. On Swarm, bench-api uses Docker "
            "config server_env (same as server) — fix DB_* there and redeploy."
        )
    elif "connection" in err or "operationalerror" in type(exc).__name__.lower():
        hint = (
            "Postgres unreachable from bench-api. Check DB_HOST/DB_PORT/DB_USER "
            "(Supabase pooler :6543 needs user postgres.<project-ref>)."
        )
    return hint
