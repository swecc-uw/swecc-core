# bench

The `bench` product folder hosts the BenchAnything backend inside swecc-core. It is **one product, three containers** (the UI lives in a separate repo):

| Subdir | Compose service | Port | Purpose |
|---|---|---|---|
| `api/`     | `bench-api`     | 8000 | FastAPI HTTP server (main control plane, websocket trace stream) |
| `sandbox/` | `bench-sandbox` | 8001 | Clones submitted env repos and proxies HTTP traffic to them |
| `worker/`  | `bench-worker`  | —    | Standalone HTTP poller; pulls queued bench jobs from the API and runs models against them |

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
docker compose up bench-api bench-sandbox bench-worker
```

Add API keys to root `.env` (see `.env.example` — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `XAI_API_KEY`).

## Tests

```bash
make test-bench-api
make test-bench-sandbox
make test-bench-worker
```

## Database

The bench schema is a Django app at `services/server/server/bench/` and lives in the shared `swecc` Postgres database. `swecc-server` runs `python manage.py migrate` on startup, so the seven `bench_*` tables (`bench_domain`, `bench_run`, `bench_episode`, `bench_leaderboard`, `bench_developerenvironment`, `bench_benchjob`, `bench_environmentusage`) are provisioned automatically — no manual setup, no separate database, no init script.

`bench-api` is a FastAPI service but it talks to the database through Django's async ORM (`Model.objects.acreate()` / `aget()` / `aupdate_or_create()`, etc.). It bootstraps Django in standalone mode at boot:

- `bench-api`'s Dockerfile copies `services/server/server/bench/` into the image so `import bench` resolves.
- `app/main.py` calls `django.setup()` before any router import.
- `app/django_settings.py` is a minimal settings module with just `INSTALLED_APPS = ["bench.apps.BenchConfig"]` and a `DATABASES["default"]` block populated from the shared `DB_HOST` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` env vars.

To add or change a bench table, edit `services/server/server/bench/models.py` and run `docker compose exec server bash -c "cd server && python manage.py makemigrations bench"` — commit the resulting `0002_*.py` file alongside the model change.

## Auth (branch `auth`)

- **Members:** JWT from swecc-server `GET /auth/jwt/` (validated via shared `packages/swecc-jwt`, same as sockets).
- **Guests:** `POST /v1/auth/guest` → Bearer guest token or `bench_guest` cookie.
- **Teams:** create team → 4-char `join_code`; join with `POST /v1/teams/join` (max 4 members). No owner-direct add.
- **CLI:** `python -m bench_common.cli auth login|guest|whoami` and `team create|join|list`.
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
