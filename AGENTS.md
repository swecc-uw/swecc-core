# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo shape

Python monorepo for SWECC's backend. Each service in `services/` is independently built, tested, and deployed; all share one root `.env`, one root `docker-compose.yml`, and one Postgres / Redis / RabbitMQ stack defined at the root.

| Service | Port | Stack | Purpose |
|---|---|---|---|
| `services/server` | 8000 | Django + DRF (Postgres) | Main API: auth, members, interview, mentorship, resume, etc. Owns all DB migrations. |
| `services/sockets` | 8004 | FastAPI (uvicorn) | WebSocket server for real-time features. |
| `services/ai` | 8008 | FastAPI (uvicorn) | LLM service (resume review via Gemini). Consumes from RabbitMQ. |
| `services/chronos` | 8002 | FastAPI (uvicorn) | Metrics collection; mounts the host docker socket. |
| `services/bot` | — | discord.py | Discord bot. Calls server API + publishes to RabbitMQ. |
| `services/scheduler` | — | bash + cron | Cron job runner (optional locally — commented out in compose). |
| `services/bench/{api,sandbox,worker}` | 8010 (api) | FastAPI | BenchAnything backend (LLM eval). See "Bench" below. |

Top-level scripts:
- `s/lib.sh` — shared bash helpers; canonical `SERVICES` list (used by build/lint/deploy).
- `s/ci/build.sh`, `s/ci/lint.sh`, `s/ci/test.sh` — service-aware CI helpers.
- `s/ops/deploy.sh` — Docker Swarm deploy (CI-only path; do not run locally).
- `run_tests.sh`, `Makefile` — unified Python test runner (see Testing).
- `setup_tests.sh` — creates `venv/` and installs every service's test deps.

## Common commands

### Local dev (Docker)

```bash
docker compose up                          # everything
docker compose up server bot               # subset
docker compose --profile with-nginx up     # add nginx reverse proxy on :80
docker compose --profile bench-worker up   # bench-worker is opt-in (profile)
```

Requires `.env` at repo root (template in `.env.example`; ask @elimelt for the real file). `server` runs `python manage.py migrate` on startup — `bench-api` depends on this because it shares the same Postgres database for `bench_*` tables.

### Tests

The Makefile and `run_tests.sh` wrap pytest for each service. **You must activate `venv` first** (created by `./setup_tests.sh`):

```bash
source venv/bin/activate

make test                  # all services
make test-ai               # one service
make test-bench            # all three bench-* services
make test-coverage         # all services with coverage
./run_tests.sh ai bot      # arbitrary subset
./run_tests.sh -v ai       # verbose
```

Server (Django) tests use `services/server/run_tests.py`, which forces SQLite in-memory and only runs `resume_review` and `contentManage` apps — adding a new Django app means editing that script to register it.

To run a single pytest test:
```bash
cd services/<svc> && python3 -m pytest tests/test_foo.py::TestBar::test_baz -v
```

### Lint

Pre-commit (black, isort, flake8, line-length 100) is enforced in CI. Locally:
```bash
pre-commit run --all-files
./s/ci/lint.sh <service> --fix    # auto-fix one service
```

### Build / deploy

```bash
./s/ci/build.sh <service|all> [--push]   # builds swecc/swecc-<service>:latest
```

Deploy is GitHub-Actions-driven on push to `main` — path filters in `.github/workflows/deploy-*.yml` trigger per-service deploys. `s/ops/deploy.sh` runs on the swarm host (`docker service update --update-order start-first` for zero downtime); avoid invoking it from a dev machine.

## Architecture notes worth knowing upfront

**Shared infra, separate services.** Postgres, Redis, and RabbitMQ live in the root `docker-compose.yml` and every service connects via `DB_HOST=swecc-db-instance` / `REDIS_HOST=swecc-redis-instance` / `RABBIT_HOST=swecc-rabbitmq-instance`. Services do *not* own their own infra containers.

**`server` is the source of truth for the DB schema.** Every Django app under `services/server/server/` (including `bench`) defines models; `server` runs `manage.py migrate` at boot. Other services that touch the DB (currently just `bench-api`) connect to the same database and rely on `server` having migrated first — note the `depends_on: server: service_started` on `bench-api`.

**Bench is one product, three containers.** `services/bench/{api,sandbox,worker}` are independently deployed but share `services/bench/common/bench_common/` (a pip-installable kernel). Build contexts are non-standard so the Dockerfiles can `COPY common/` into the image — `bench-api`'s context is even wider (`./services`) because it also embeds the Django bench app from `services/server/server/bench/`. See `s/lib.sh:build_context()` and `services/bench/README.md` for the full picture. `bench-api` is FastAPI but uses Django's async ORM — it calls `django.setup()` at boot with a minimal `app/django_settings.py`.

**Env-author CLI (PyPI):** Only **`swecc-mesocosm`** is published (`packages/swecc-mesocosm/`). Users run **`mesocosm`** only (`mesocosm init`, `mesocosm run local`, `mesocosm auth login`, …). Implementation lives in `bench_common` (`services/bench/common/`) and is bundled into that wheel — not a separate PyPI package and no `bench` console script. See `packages/swecc-mesocosm/PACKAGING.md`.

**RabbitMQ is the cross-service bus.** `server` and `bot` publish; `ai` and `sockets` consume. Each service owns its `mq/` module with producer/consumer code; there is no shared client library.

**Per-service deploys with shared CI.** `.github/workflows/ci.yml` runs lint+test for *every* service on every PR (matrix build, fail-fast off). `detect-changes` then path-filters which services actually need a Docker image rebuild — only those run the `build` job. Each `deploy-<service>.yml` has its own path filter so a server-only PR doesn't redeploy the bot.

**Swarm gateway DNS.** Production runs Docker Swarm behind SWAG (nginx). `s/lib.sh:swarm_gateway_dns()` registers each service under a `swecc_stack_<svc>` network alias on `prod_swecc-network` so SWAG upstreams resolve. New services need an alias registered via `swarm_ensure_gateway_alias()` (the deploy script does this automatically).

**Two compose configs for nginx.** `infra/nginx.dev.conf` (used by `--profile with-nginx`) is for local dev; `infra/nginx.conf` is the prod reference. They are not interchangeable.

## Pitfalls

- The `s/lib.sh` `SERVICES` array is canonical. If you add a service, register it there or `validate_service` will reject it across build/lint/deploy.
- `services/server/run_tests.py` hard-codes which Django apps get tested. New apps with tests need to be added explicitly.
- `bench-worker` is in a compose `profiles: [bench-worker]` block — it does *not* start with a bare `docker compose up`.
- Coverage flag (`--coverage`) is a no-op for the server (Django) — only pytest services emit coverage.
- Server `docker-compose.dev.yml` / `docker-compose.local.*.yml` files exist for legacy server-only dev workflows. Prefer the root `docker-compose.yml` for new work.
