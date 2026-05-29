# bench

The `bench` product folder hosts the BenchAnything backend inside swecc-core. It is **one product, three containers** (the UI lives in a separate repo):

| Subdir | Compose service | Port | Purpose |
|---|---|---|---|
| `api/`     | `bench-api`     | 8000 | FastAPI HTTP server (main control plane, websocket trace stream) |
| `sandbox/` | `bench-sandbox` | 8001 | Clones submitted env repos and proxies HTTP traffic to them |
| `worker/`  | `bench-worker`  | —    | Consumes full-bench jobs from RabbitMQ (or HTTP-polls the API when `ORCH_MQ_ENABLED` is off) |

Plus two non-container directories:

| Subdir | Purpose |
|---|---|
| `common/`   | `bench_common` shared kernel (core, storage, runtime, eval, env_sdk, techniques, orchestrator, inference CLI). Installed as a wheel by `api/Dockerfile` and `sandbox/Dockerfile`. |
| `template/` | Scaffolding users copy when authoring a new env. |
| `docs/`     | Design doc, examples, change log. |
| `scripts/`  | Local-dev helpers (seed example domain, run a single episode, etc.). |

## How the build context works

Each Dockerfile lives in its subdir but is built with `context: ./services/bench` so it can `COPY common/ ...` plus its own `<sub>/`. See the root `docker-compose.yml`:

```yaml
bench-api:
  build:
    context: ./services/bench
    dockerfile: api/Dockerfile
```

## Local dev

From the swecc-core repo root:

```bash
docker compose up bench-api bench-sandbox
docker compose --profile bench-worker up   # optional worker
```

Add API keys to root `.env` (see `.env.example` — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`).

### RabbitMQ (production / scaled local)

Set `ORCH_MQ_ENABLED=1` on **bench-api** and **bench-worker** (and `BENCH_RABBIT_USER` / `BENCH_RABBIT_PASS` in `.env`, same pattern as other services).

| Routing key | Queue | Producer | Consumer |
|---|---|---|---|
| `bench.run.execute` | `bench.run-queue` | bench-api (`POST /v1/runs`) | bench-api (when `ORCH_MQ_CONSUME_RUNS=1`) |
| `bench.job.execute` | `bench.job-queue` | bench-api (`POST /v1/bench/full`) | bench-worker |

Exchange: `swecc-bench-exchange` (topic). Scale throughput by running multiple **bench-worker** replicas (jobs) and/or **bench-api** replicas (runs). With multiple API replicas, use a **shared** `ORCH_TRACE_DIR` volume so WebSocket trace streaming can read episode logs written by any replica.

Provision prod RabbitMQ user: `s/ops/rabbitmq.sh create-user bench-api`.

## Tests

```bash
make test-bench-api
make test-bench-sandbox
make test-bench-worker
```

## Database

The bench schema is a Django app at `services/server/server/bench/` and lives in the shared `swecc` Postgres database. `swecc-server` runs `python manage.py migrate` on startup (compose and production). Tables are provisioned automatically — no separate database, no init script.

**Do not run `makemigrations` in production.** Committed files under `bench/migrations/` are the source of truth; CI runs `check_bench_migrations.py` and fails PRs when models drift. Deploy workflows for `bench-api` and `bench-worker` always roll out `server` first so migrations apply before bench services start.

`bench-api` is a FastAPI service but it talks to the database through Django's async ORM (`Model.objects.acreate()` / `aget()` / `aupdate_or_create()`, etc.). It bootstraps Django in standalone mode at boot:

- `bench-api`'s Dockerfile copies `services/server/server/bench/` into the image so `import bench` resolves.
- `app/main.py` calls `django.setup()` before any router import.
- `app/django_settings.py` is a minimal settings module with just `INSTALLED_APPS = ["bench.apps.BenchConfig"]` and a `DATABASES["default"]` block populated from the shared `DB_HOST` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` env vars.

To add or change a bench table:

1. Edit `services/server/server/bench/models.py`.
2. Run `docker compose exec server bash -c "cd server && python manage.py makemigrations bench"`.
3. Commit the new `bench/migrations/000N_*.py` in the same PR as the model change.

Verify locally: `cd services/server && python check_bench_migrations.py`.

### Prod migration troubleshooting

If production broke after a deploy that ran `makemigrations` on boot (auto-generated migration files not in git), deploy `server` with committed migrations only, then run `python manage.py migrate bench` after backup/review of any orphan rows in `django_migrations`.

## Auth (branch `auth`)

- **Members:** JWT from swecc-server `GET /auth/jwt/` (validated via shared `packages/swecc-jwt`, same as sockets).
- **Guests:** `POST /v1/auth/guest` → Bearer guest token or `bench_guest` cookie.
- **Teams:** create team → 4-char `join_code`; join with `POST /v1/teams/join` (max 4 members). No owner-direct add.
- **CLI:** `python -m bench_common.cli auth login|guest|whoami` and `team create|join|list`.
- **Local dev without auth:** `BENCH_AUTH_DISABLED=1`.
- **Migrate:** `docker compose exec server bash -c "cd server && python manage.py migrate bench"`.

## Auth (branch `auth`)

- **Members:** JWT from swecc-server `GET /auth/jwt/` (validated via shared `packages/swecc-jwt`, same as sockets).
- **Guests:** `POST /v1/auth/guest` → Bearer guest token or `bench_guest` cookie.
- **Teams:** create team → 4-char `join_code`; join with `POST /v1/teams/join` (max 4 members). No owner-direct add.
- **CLI (PyPI):** `mesocosm` only via `swecc-mesocosm` — `auth`, `team`, `env submit`, `run create|local|export`, `init`. See `docs/SHOWCASE_DEVELOPER.md` and `packages/swecc-mesocosm/PACKAGING.md`.
- **Local dev without auth:** `BENCH_AUTH_DISABLED=1`.
- **Migrate:** `docker compose exec server bash -c "cd server && python manage.py migrate bench"`.

## Inference CLI

The standalone benchmarking CLI ships inside `bench_common`:

```bash
docker compose run --rm bench-api python -m bench_common.inference.bench \
  --model openai/gpt-4o --domain simple-trivia --env-url http://host.docker.internal:8765
```

## Migrating from the upstream BenchAnything repo

This is a copy with import rewrites. The original project lives at https://github.com/<your-org>/BenchAnything. The mapping was:

| BenchAnything | swecc-core |
|---|---|
| `src/{core,storage,runtime,eval,env_sdk,techniques,orchestrator,inference,config.py}` | `services/bench/common/bench_common/` |
| `src/api/`     | `services/bench/api/app/` (entry point renamed `app.py` → `main.py`) |
| `src/sandbox/` | `services/bench/sandbox/app/` |
| `src/worker/bench_worker.py` | `services/bench/worker/app/worker.py` |
| `template/`, `docs/`, `scripts/` | same paths under `services/bench/` |
| `ui/`          | _not migrated; lives in a separate repo and points at `bench-api` over HTTP_ |
| `mcp/bench_anything_mcp/` | `services/mcp/servers/bench-anything/bench_anything_mcp/` |

Imports were rewritten:
- `from src.api.routes import X` → `from app.routes import X` (inside `bench-api`)
- `from src.sandbox import X` → `from app import X` (inside `bench-sandbox`)
- everything else `from src.<kernel>` → `from bench_common.<kernel>`
