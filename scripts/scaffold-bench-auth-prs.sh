#!/usr/bin/env bash
# Split auth commit into 5 stacked branches and open draft PRs via gh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

AUTH_COMMIT="${AUTH_COMMIT:-auth}"
BASE="${BASE:-main}"

if ! git rev-parse -q "$AUTH_COMMIT" >/dev/null; then
  echo "Missing commit/branch: $AUTH_COMMIT" >&2
  exit 1
fi

# Prefer bench-api tip on auth lineage when main lags navneeth-patches bench work.
if git merge-base --is-ancestor "$BASE" "$AUTH_COMMIT" 2>/dev/null; then
  :
else
  BASE="$(git merge-base "$BASE" "$AUTH_COMMIT")"
fi

PR1_BASE="${PR1_BASE:-$BASE}"
echo "Using PR1 base: $PR1_BASE (auth tip: $(git rev-parse --short "$AUTH_COMMIT"))"

checkout_auth() {
  git checkout "$AUTH_COMMIT" -- "$@"
}

write_main_pr1() {
  cat > services/bench/api/app/main.py <<'PY'
"""
FastAPI application entry point.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager

os.environ["DJANGO_SETTINGS_MODULE"] = "app.django_settings"
import django  # noqa: E402
from django.conf import settings as django_settings  # noqa: E402

django.setup()

if "bench.apps.BenchConfig" not in django_settings.INSTALLED_APPS:
    raise RuntimeError(
        "Wrong Django settings loaded (expected app.django_settings). "
        "Unset DJANGO_SETTINGS_MODULE in server_env or ensure bench-api entrypoint runs first."
    )

import structlog  # noqa: E402
from app.middleware.auth import PrincipalMiddleware  # noqa: E402
from app.routes import (  # noqa: E402
    auth_routes,
    bench,
    developer,
    domains,
    leaderboard,
    runs,
    techniques,
    test,
)
from bench_common.config import settings as bench_settings  # noqa: E402
from bench_common.storage.database import init_db  # noqa: E402
from bench_common.storage.trace_store import trace_store  # noqa: E402
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

log = structlog.get_logger()
GATEWAY_PREFIX = bench_settings.gateway_prefix


def _public_path(path: str) -> str:
    return f"{GATEWAY_PREFIX}{path}" if GATEWAY_PREFIX else path


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    log.info("database_ready")
    yield


app = FastAPI(
    title="BenchAnything",
    version="0.1.0",
    description="Distributed evaluation protocol for AI agent benchmarks",
    lifespan=lifespan,
    root_path=GATEWAY_PREFIX,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(PrincipalMiddleware)

app.include_router(auth_routes.router)
app.include_router(domains.router)
app.include_router(runs.router)
app.include_router(test.router)
app.include_router(leaderboard.router)
app.include_router(techniques.router)
app.include_router(developer.router)
app.include_router(bench.router)


@app.get("/")
async def root() -> dict:
    return {
        "service": "BenchAnything",
        "version": "0.1.0",
        "docs": _public_path("/docs"),
        "redoc": _public_path("/redoc"),
        "health": _public_path("/health"),
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


@app.websocket("/v1/ws/episodes/{episode_id}/trace")
async def stream_trace(websocket: WebSocket, episode_id: str) -> None:
    await websocket.accept()
    sent = 0
    try:
        while True:
            events = await trace_store.read(episode_id)
            for event in events[sent:]:
                await websocket.send_text(event.model_dump_json())
                sent += 1
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                msg = json.loads(data)
                if msg.get("command") == "cancel":
                    break
            except asyncio.TimeoutError:
                pass
            except Exception:
                break
            if events and events[-1].event_type == "episode_end":
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()
PY
}

write_main_pr2() {
  # PR2: add gallery + me routers (still no teams)
  python3 - <<'PY'
from pathlib import Path
p = Path("services/bench/api/app/main.py")
text = p.read_text()
if "gallery" not in text:
    text = text.replace(
        "    auth_routes,\n    bench,",
        "    auth_routes,\n    bench,\n    gallery,\n    leaderboard,\n    me_routes,",
    )
    text = text.replace("    leaderboard,\n    runs,", "    runs,")
    text = text.replace(
        "app.include_router(auth_routes.router)\napp.include_router(domains.router)",
        "app.include_router(auth_routes.router)\n"
        "app.include_router(gallery.router)\n"
        "app.include_router(me_routes.router)\n"
        "app.include_router(domains.router)",
    )
    # fix duplicate leaderboard import
    lines = []
    seen_gallery = seen_me = False
    for line in text.splitlines():
        if "from app.routes import" in line:
            lines.append(line)
            continue
        if line.strip() == "gallery," and seen_gallery:
            continue
        if line.strip() == "me_routes," and seen_me:
            continue
        if line.strip() == "gallery,":
            seen_gallery = True
        if line.strip() == "me_routes,":
            seen_me = True
        lines.append(line)
    p.write_text("\n".join(lines) + "\n")
PY
  checkout_auth services/bench/api/app/main.py
}

write_main_pr3() {
  checkout_auth services/bench/api/app/main.py
}

commit_if_dirty() {
  local msg="$1"
  if ! git diff --quiet || ! git diff --cached --quiet; then
    git add -A
    git commit -m "$msg"
  fi
}

create_pr() {
  local branch="$1"
  local base="$2"
  local title="$3"
  local body="$4"
  git push -u origin "$branch" --force-with-lease
  gh pr create --draft --base "$base" --head "$branch" --title "$title" --body "$body"
}

# --- PR1 ---
git checkout "$PR1_BASE" -B bench-auth/pr-1-schema-jwt
checkout_auth \
  packages/swecc-jwt \
  services/sockets/app/auth.py \
  services/sockets/Dockerfile \
  services/server/server/bench/models.py \
  services/server/server/bench/migrations/0002_auth_teams.py \
  services/bench/common/bench_common/auth \
  services/bench/api/app/auth/__init__.py \
  services/bench/api/app/auth/principal.py \
  services/bench/api/app/auth/resolve.py \
  services/bench/api/app/auth/guest_tokens.py \
  services/bench/api/app/auth/deps.py \
  services/bench/api/app/auth/policy.py \
  services/bench/api/app/middleware/auth.py \
  services/bench/api/app/routes/auth_routes.py \
  services/bench/api/Dockerfile \
  services/bench/api/requirements.txt \
  docker-compose.yml \
  s/lib.sh
# pyproject: only jwt dep + no bench script yet
git show "$AUTH_COMMIT":services/bench/common/pyproject.toml > services/bench/common/pyproject.toml
python3 - <<'PY'
from pathlib import Path
t = Path("services/bench/common/pyproject.toml").read_text()
if "[project.scripts]" in t:
    t = t.split("[project.scripts]")[0].rstrip() + "\n\n"
    Path("services/bench/common/pyproject.toml").write_text(t)
PY
write_main_pr1
commit_if_dirty "feat(bench): schema, swecc-jwt, and auth middleware (PR1)"

# --- PR2 ---
git checkout -B bench-auth/pr-2-routes-gallery bench-auth/pr-1-schema-jwt
checkout_auth \
  services/bench/api/app/auth/access.py \
  services/bench/api/app/routes/gallery.py \
  services/bench/api/app/routes/me_routes.py \
  services/bench/api/app/routes/runs.py \
  services/bench/api/app/routes/domains.py \
  services/bench/api/app/routes/developer.py \
  services/bench/api/app/routes/bench.py \
  services/bench/common/bench_common/config.py \
  services/bench/common/bench_common/storage/django_store.py \
  services/bench/common/bench_common/orchestrator/service.py \
  services/bench/common/bench_common/storage/dev_sync.py
write_main_pr3  # full main from auth (gallery+me, no teams in import - auth main has teams)
# Remove teams from main for PR2
python3 - <<'PY'
from pathlib import Path
p = Path("services/bench/api/app/main.py")
t = p.read_text()
for token in ("    teams,\n", "app.include_router(teams.router)\n"):
    t = t.replace(token, "")
p.write_text(t)
PY
commit_if_dirty "feat(bench): secure routes, gallery, and /v1/me (PR2)"

# --- PR3 ---
git checkout -B bench-auth/pr-3-teams-api bench-auth/pr-2-routes-gallery
checkout_auth \
  services/bench/api/app/routes/teams.py \
  services/bench/api/app/services
write_main_pr3
commit_if_dirty "feat(bench): teams API and join codes (PR3)"

# --- PR4 ---
git checkout -B bench-auth/pr-4-cli bench-auth/pr-3-teams-api
checkout_auth \
  services/bench/common/bench_common/cli \
  services/bench/common/bench_common/env_sdk/register.py \
  services/bench/common/bench_common/env_sdk/registration.py \
  services/bench/common/pyproject.toml
commit_if_dirty "feat(bench): unified CLI with auth and team commands (PR4)"

# --- PR5 ---
git checkout -B bench-auth/pr-5-tests-worker bench-auth/pr-4-cli
checkout_auth \
  services/bench/api/app/auth/worker.py \
  services/bench/api/tests/test_auth_teams.py \
  services/bench/api/tests/test_policy.py \
  services/bench/worker/app/worker.py \
  services/server/server/bench/management \
  services/bench/README.md \
  .env.example \
  services/bench/common/tests/test_supported_models.py
# Re-apply worker route guards on bench.py
checkout_auth services/bench/api/app/routes/bench.py
commit_if_dirty "test(bench): auth tests, worker token, cleanup job (PR5)"

# Restore auth branch pointer
git checkout auth

echo "Done scaffolding branches. Push + create PRs..."
create_pr bench-auth/pr-1-schema-jwt "$PR1_BASE" \
  "feat(bench): schema, swecc-jwt, and guest auth (PR 1/5)" \
  "## Summary
- Django bench migration for guest sessions, teams, and actor columns
- Shared \`packages/swecc-jwt\` extracted from sockets
- bench-api principal middleware and guest session endpoints
- \`BENCH_AUTH_DISABLED\` supported for local dev

## Test plan
- [ ] \`docker compose exec server bash -c 'cd server && python manage.py migrate bench'\`
- [ ] \`POST /v1/auth/guest\` returns token
- [ ] Member JWT from server validates on bench-api"

create_pr bench-auth/pr-2-routes-gallery bench-auth/pr-1-schema-jwt \
  "feat(bench): secure routes, gallery, and /v1/me (PR 2/5)" \
  "## Summary
- Principal checks on runs, domains, developer, and bench test routes
- Public gallery and authenticated /v1/me endpoints

## Test plan
- [ ] Guest can run allowlisted demo domains
- [ ] Member runs are private by default
- [ ] Gallery lists guest public runs"

create_pr bench-auth/pr-3-teams-api bench-auth/pr-2-routes-gallery \
  "feat(bench): teams API (PR 3/5)" \
  "## Summary
- Team create/join via 4-char codes (max 4 members)
- Team runs and environments endpoints

## Test plan
- [ ] Create team, join with code, leave and transfer ownership"

create_pr bench-auth/pr-4-cli bench-auth/pr-3-teams-api \
  "feat(bench): bench CLI auth and teams (PR 4/5)" \
  "## Summary
- \`bench auth login|guest|whoami\`
- \`bench team *\` and \`bench env *\` commands
- Domain registration uses authenticated session

## Test plan
- [ ] \`bench auth login\` then \`bench team list\`"

create_pr bench-auth/pr-5-tests-worker bench-auth/pr-4-cli \
  "test(bench): tests, worker auth, docs (PR 5/5)" \
  "## Summary
- pytest for JWT and guest policy
- Worker sends \`BENCH_WORKER_TOKEN\` to job endpoints
- Guest cleanup management command and README

## Test plan
- [ ] \`pytest services/bench/api/tests/test_auth_teams.py\`
- [ ] Worker claims jobs with token set"

echo "All draft PRs created."
