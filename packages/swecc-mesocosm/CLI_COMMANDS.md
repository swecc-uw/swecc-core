# mesocosm CLI reference

Complete parameter reference for `mesocosm` (swecc-mesocosm **0.2.12** era, `cli-updates` branch). Implementation is split between **bench_common** (`services/bench/common/bench_common/cli/main.py`, argparse) and **Typer** (`packages/swecc-mesocosm/swecc_mesocosm/cli.py`), unified at the `mesocosm` entry point.

**See also:** [README.md](./README.md) (install and workflows), [PACKAGING.md](./PACKAGING.md) (routing), and **`LOCAL_DEV.md`** in your repo after `mesocosm init` (Ollama + adapter loop).

---

## Quick reference

| Command | Arguments / flags | Description (≤12 words) |
| --- | --- | --- |
| *(root)* | `-V`, `--version` | Show mesocosm version and exit |
| `auth login` | `--server-url` | Log in; prompts for username and password |
| `auth token` | — | Print saved member JWT for curl or scripts |
| `auth guest` | `--bench-url` | Create guest session on bench-api |
| `auth whoami` | `--bench-url` | Show current principal via GET /v1/me |
| `auth logout` | — | Clear saved credentials file |
| `team create` | `--name`; `--use` | Create team; optionally set active |
| `team join` | `CODE` | Join team using invite code |
| `team list` | — | List teams you belong to |
| `team show` | `TEAM_ID` | Print team details as JSON |
| `team use` | `TEAM_ID` | Set active team in credentials |
| `team clear` | — | Clear active team; use solo default |
| `team runs` | `TEAM_ID` | List runs for a team |
| `team code show` | `TEAM_ID` | Show team including join code |
| `team code regenerate` | `TEAM_ID` | Rotate team join invite code |
| `team members remove` | `TEAM_ID`; `--user-id` | Remove member from team (owner) |
| `team transfer` | `TEAM_ID`; `--user-id` | Transfer team ownership to user |
| `team leave` | `TEAM_ID` | Leave a team you belong to |
| `team delete` | `TEAM_ID` | Delete a team (owner) |
| `init` | `--dir`; `--force` | Scaffold benchanything.json, adapter, env, showcase |
| `run local` | see below | Bench locally with Ollama and benchanything.json |
| `env submit` | `--name`; `--github-url`; … | Submit GitHub repo as developer environment |
| `env list` | `--team`; `--solo` | List your developer environments |
| `run create` | `--domain`; `--vow-version`; … | Start platform bench run via API |
| `run export` | `RUN_ID`; `-o` / `--output` | Download run JSON for showcase or replay |
| `register` | `domain.py`; `--auto-id`; `--publish` | Legacy register domain.py; prefer env submit |
| `doctor` | `--base-url`; `--local` | Check bench-api reachability; local checks adapter |
| `validate` | `FILE` or `-` | Validate domain JSON against policy constraints |
| `eval test` | `--domain-id`; … | Run single test episode via bench-api |
| `eval run` | `--domain-id`; … | Run multi-episode eval with scoring aggregation |
| `run get` | `RUN_ID`; `--base-url` | Fetch run status and aggregate scores |
| `run episodes` | `RUN_ID`; `--traces`; `--base-url` | List episodes for a run; optional traces |

Run `mesocosm --help` or `mesocosm run --help` for the Rich command tree (`help_text.py`).

---

## Global configuration

### Credentials file

| Item | Description |
| --- | --- |
| **Default path** | `~/.config/swecc/bench_credentials.json` |
| **Override** | Set `SWECC_BENCH_CREDENTIALS` to another file path. |
| **Typical keys** | `mode` (`member` \| `guest`), `token`, `server_url`, `bench_url`, `active_team_id` (optional). |

Written by `auth login`, `auth guest`, `team use`, `team clear`, and `team create --use`. Cleared by `auth logout`.

### Environment variables

| Variable | Used by | Description |
| --- | --- | --- |
| `MESOCOSM_LOCAL` | URL defaults, `doctor --local` | When set to `1`, `true`, `yes`, or `on`, use local docker URLs (`127.0.0.1:8000` server, `:8010` bench-api, `:8765` adapter) unless overridden. See [README.md](./README.md#configure). |
| `MESOCOSM_BASE_URL` | Typer (`--base-url`), URL resolution | bench-api base URL. Production must include `/bench` (e.g. `https://api.swecc.org/bench`). |
| `SWECC_BENCH_URL` | bench_common URL resolution | Alias for bench-api base URL (same precedence as `MESOCOSM_BASE_URL`). |
| `BENCH_API_URL` | bench_common URL resolution | Third alias for bench-api base URL. |
| `SWECC_SERVER_URL` | `auth login` default | swecc-server base URL for member login (default prod: `https://api.swecc.org`). |
| `SWECC_BENCH_TOKEN` | API calls without `auth login` | Member JWT for scripts/CI; used by `get_bench_session()` when set. |
| `SWECC_BENCH_GUEST_TOKEN` | API calls | Guest token; forces guest mode when set. |
| `SWECC_BENCH_CREDENTIALS` | Credential store | Path to JSON credentials file. |
| `MESOCOSM_ENV_URL` | `doctor --local` | Override env adapter URL (default `http://127.0.0.1:8765`). |
| `MESOCOSM_ADAPTER_URL` | `doctor --local` | Alias for env adapter URL. |
| `BENCH_AUTH_DISABLED` | bench_common session (dev) | When `1`/`true`/`yes`, skip auth and use empty bearer (local bench-api dev only). |

**Resolution order (member bench-api URL):** CLI `--bench-url` / `--base-url` → env vars above → saved `bench_url` in credentials (with stale-local fix) → derive from `server_url` → `MESOCOSM_LOCAL` → production default.

**Guest default URL:** `auth guest` uses CLI `--bench-url` or env bench URL vars only — **not** saved credentials and **not** `MESOCOSM_LOCAL` — defaulting to `https://api.swecc.org/bench` when unset.

### Global CLI flags

| Flag | Applies to | Description |
| --- | --- | --- |
| `--bench-url` | All **bench_common** commands (`auth`, `team`, `env`, `init`, `register`, `run create` \| `local` \| `export`) | Parent argparse flag on `mesocosm`. Overrides bench-api base URL for that invocation. Default from env/credentials (see above). |
| `--base-url` | Typer commands (`doctor`, `validate`, `eval`, `run get`, `run episodes`) | Same role as `--bench-url`; also reads `MESOCOSM_BASE_URL`. Default from `swecc_mesocosm.settings` / `default_bench_api_url()`. |
| `-V`, `--version` | Root (Typer) | Print package version and exit. |

### Active team context

Many platform commands attach `team_id` from credentials `active_team_id`, unless you pass `--team TEAM_ID` or `--solo` (force no team). Set active team with `mesocosm team use TEAM_ID` or `team create --use`.

---

## `mesocosm` (root)

**Summary:** Entry point; `mesocosm --help` prints the full command tree.

| Parameter | Required | Description |
| --- | --- | --- |
| `-V`, `--version` | No | Eager option: print `mesocosm <version>` and exit (Typer callback). |
| `--help` | No | Show unified help (`help_text.print_root_help`) or Typer help for subcommands. |

**Routing:** `auth`, `team`, `env`, `init`, `register`, and `run create|local|export` → bench_common. `doctor`, `validate`, `eval`, `run get|episodes` → Typer. `mesocosm run` alone → `print_run_help`.

---

## `mesocosm auth login`

**Summary:** Interactive member login via swecc-server; saves JWT and bench URL to credentials.

| Parameter | Required | Description |
| --- | --- | --- |
| `--server-url` | No | swecc-server base URL for `/auth/login/` and JWT fetch. Default: `SWECC_SERVER_URL`, else `MESOCOSM_LOCAL` → `http://127.0.0.1:8000`, else `https://api.swecc.org`. |
| `--bench-url` | No | Global parent flag. bench-api URL stored in credentials after login. Default derived from server (prod → `https://api.swecc.org/bench`, local server → `:8010`). |
| *(interactive)* | Yes | Prompts for **username** (default: OS username) and **password** via stdin/getpass. No `--username` / `--password` flags. Password is sent to the server over HTTPS only; not stored in shell history. |

**After success:** Writes `mode: member`, `token`, `server_url`, `bench_url` to credentials. For CI, use `SWECC_BENCH_TOKEN` instead of login ([README.md](./README.md#configure)).

---

## `mesocosm auth token`

**Summary:** Print the saved member JWT for curl or scripts.

| Parameter | Required | Description |
| --- | --- | --- |
| `--bench-url` | No | Global parent flag (unused for output; session not required). |

**Requires:** Prior `auth login` with `mode: member`. Exits with error if only guest credentials exist.

---

## `mesocosm auth guest`

**Summary:** Create a short-lived guest session on bench-api (no swecc-server account).

| Parameter | Required | Description |
| --- | --- | --- |
| `--bench-url` | No | bench-api base URL for `POST /v1/auth/guest`. Default: env `MESOCOSM_BASE_URL` / `SWECC_BENCH_URL` / `BENCH_API_URL`, else **production** `https://api.swecc.org/bench` (ignores saved credentials and `MESOCOSM_LOCAL`). |

**After success:** Saves `mode: guest`, `token`, `bench_url`. Guest cannot run member-only commands (`team *`, `env submit`, etc.).

---

## `mesocosm auth whoami`

**Summary:** Call `GET /v1/me` and print JSON principal.

| Parameter | Required | Description |
| --- | --- | --- |
| `--bench-url` | No | Global flag; combined with credentials via `whoami_bench_api_url()`. Guest sessions use saved guest `bench_url` when set. |

**Errors:** Connection failures print hints for prod vs local docker. If guest token is rejected at the resolved URL, suggests re-running `auth guest`.

---

## `mesocosm auth logout`

**Summary:** Delete the credentials file.

| Parameter | Required | Description |
| --- | --- | --- |
| — | — | No arguments. Removes `SWECC_BENCH_CREDENTIALS` path (default under `~/.config/swecc/`). |

---

## `mesocosm team create`

**Summary:** Create a team (member auth required).

| Parameter | Required | Description |
| --- | --- | --- |
| `--name` | Yes | Display name for the new team. |
| `--use` | No | If set, save returned `team_id` as `active_team_id` in credentials. |
| `--bench-url` | No | Global parent flag for bench-api session. |

**Output:** Prints `team_id` and `join_code` (member count / max).

---

## `mesocosm team join`

**Summary:** Join a team with an invite code.

| Parameter | Required | Description |
| --- | --- | --- |
| `CODE` | Yes | Positional invite code (normalized to uppercase). |
| `--bench-url` | No | Global parent flag. |

---

## `mesocosm team list`

**Summary:** List teams you belong to (one line per team).

| Parameter | Required | Description |
| --- | --- | --- |
| `--bench-url` | No | Global parent flag. |

---

## `mesocosm team show`

**Summary:** Fetch team details as JSON.

| Parameter | Required | Description |
| --- | --- | --- |
| `TEAM_ID` | Yes | Positional team UUID. |
| `--bench-url` | No | Global parent flag. |

---

## `mesocosm team use`

**Summary:** Set active team in credentials (no API call).

| Parameter | Required | Description |
| --- | --- | --- |
| `TEAM_ID` | Yes | Positional team UUID stored as `active_team_id`. |
| `--bench-url` | No | Global parent flag; may refresh `bench_url` in creds if missing. |

---

## `mesocosm team clear`

**Summary:** Remove `active_team_id` from credentials (solo default for env/runs).

| Parameter | Required | Description |
| --- | --- | --- |
| — | — | No arguments. |

---

## `mesocosm team runs`

**Summary:** List runs for a team (`GET /v1/teams/{id}/runs`).

| Parameter | Required | Description |
| --- | --- | --- |
| `TEAM_ID` | Yes | Positional team UUID. |
| `--bench-url` | No | Global parent flag. |

---

## `mesocosm team code show`

**Summary:** Same as `team show` (includes join code in response).

| Parameter | Required | Description |
| --- | --- | --- |
| `TEAM_ID` | Yes | Positional team UUID. |
| `--bench-url` | No | Global parent flag. |

---

## `mesocosm team code regenerate`

**Summary:** Rotate the team join invite code (owner).

| Parameter | Required | Description |
| --- | --- | --- |
| `TEAM_ID` | Yes | Positional team UUID. |
| `--bench-url` | No | Global parent flag. |

---

## `mesocosm team members remove`

**Summary:** Remove a member from a team (owner).

| Parameter | Required | Description |
| --- | --- | --- |
| `TEAM_ID` | Yes | Positional team UUID. |
| `--user-id` | Yes | Integer user id to remove. |
| `--bench-url` | No | Global parent flag. |

---

## `mesocosm team transfer`

**Summary:** Transfer team ownership to another user.

| Parameter | Required | Description |
| --- | --- | --- |
| `TEAM_ID` | Yes | Positional team UUID. |
| `--user-id` | Yes | Integer user id of the new owner. |
| `--bench-url` | No | Global parent flag. |

---

## `mesocosm team leave`

**Summary:** Leave a team (`DELETE .../members/me`).

| Parameter | Required | Description |
| --- | --- | --- |
| `TEAM_ID` | Yes | Positional team UUID. |
| `--bench-url` | No | Global parent flag. |

---

## `mesocosm team delete`

**Summary:** Delete a team (owner).

| Parameter | Required | Description |
| --- | --- | --- |
| `TEAM_ID` | Yes | Positional team UUID. |
| `--bench-url` | No | Global parent flag. |

---

## `mesocosm init`

**Summary:** Scaffold a new env author repo (no API calls).

| Parameter | Required | Description |
| --- | --- | --- |
| `--dir` | No | Target directory (default: current directory `.`). |
| `--force` | No | Overwrite existing scaffold files instead of skipping. |
| `--bench-url` | No | Global parent flag (unused by init logic). |

**Writes:** `benchanything.json`, `adapter.py`, `env.py`, `requirements.txt`, `LOCAL_DEV.md`, `showcase/README.md`, `showcase/replay.example.json`. See **`LOCAL_DEV.md`** in the target dir for the Ollama + `run local` workflow ([README.md](./README.md#env-author-quick-start)).

---

## `mesocosm run local`

**Summary:** Run episodes locally via Ollama + `benchanything.json` (no platform submit).

| Parameter | Required | Description |
| --- | --- | --- |
| `--manifest` | No | Path to `benchanything.json` (default: `./benchanything.json`). |
| `--domain-id` | No | Override domain id; default from manifest or parent folder name. |
| `--model` | No | LiteLLM model id (default: `ollama/llama3.2`). Must start with `ollama/` or CLI exits. |
| `--env-url` | No | Env adapter base URL (default: `http://localhost:8765`). Start with `python adapter.py`. |
| `--episodes` | No | Number of episodes (default: `5`). |
| `--seeds` | No | Space-separated integer seeds (default: none). |
| `--system-prompt` | No | Optional system prompt passed to the agent. |
| `--temperature` | No | Sampling temperature (default: `0.0`). |
| `--max-tokens` | No | Max tokens per step (default: `512`). |
| `--parallel` | No | Max parallel episodes (default: `1`). |
| `--quiet` | No | Reduce bench progress output. |
| `--bench-url` | No | Global parent flag (unused; no bench-api call). |

**Does not** register the domain or create platform runs. See **`LOCAL_DEV.md`** after `mesocosm init`.

---

## `mesocosm env submit`

**Summary:** Submit a GitHub repo as a developer environment (member auth).

| Parameter | Required | Description |
| --- | --- | --- |
| `--name` | Yes | Human-readable environment name. |
| `--github-url` | Yes | Public GitHub repo URL; platform clones and registers domain from `benchanything.json`. |
| `--description` | No | Optional description string (default: empty). |
| `--team` | No | Explicit `team_id` for the submission (overrides active team). |
| `--solo` | No | Force solo scope (no `team_id` in payload). |
| `--bench-url` | No | Global parent flag. |

**Team scope:** Uses `active_team_id` from credentials unless `--team` or `--solo` is set.

---

## `mesocosm env list`

**Summary:** List developer environments for you (or active team).

| Parameter | Required | Description |
| --- | --- | --- |
| `--team` | No | Explicit team id filter (`scope=team`). |
| `--solo` | No | List solo-scoped environments only. |
| `--bench-url` | No | Global parent flag. |

---

## `mesocosm run create`

**Summary:** Start a bench run on the platform (`POST /v1/runs`).

| Parameter | Required | Description |
| --- | --- | --- |
| `--domain` | Yes | Target domain id (from `env submit` or legacy register). |
| `--vow-version` | Yes | Binding vow version string (e.g. `1.0.0`). |
| `--model` | Yes | Model identifier (e.g. `gemini/gemini-3.1-flash-lite`, `openai/gpt-4o-mini`). |
| `--episodes` | No | Number of episodes (default: `1`). |
| `--parallel` | No | Max parallel episodes (default: `1`). |
| `--system-prompt` | No | Optional system prompt in `agent_config`. |
| `--temperature` | No | Agent temperature (default: `0.0`). |
| `--max-tokens` | No | Agent max tokens per step (default: `512`). |
| `--team` | No | Explicit team id on the run. |
| `--solo` | No | Do not attach active team to the run. |
| `--visibility` | No | `private` or `gallery_public` (optional). |
| `--env-id` | No | Developer environment id to pin env URL/runtime. |
| `--bench-url` | No | Global parent flag. |

**Auth:** Uses `get_bench_session()` (member or guest token). Team id from active credentials unless `--solo` / `--team`.

---

## `mesocosm run export`

**Summary:** Download run JSON (traces + replay) for showcase.

| Parameter | Required | Description |
| --- | --- | --- |
| `RUN_ID` | Yes | Positional platform run id. |
| `-o`, `--output` | No | Write JSON to file; default stdout. |
| `--bench-url` | No | Global parent flag. |

**API:** `GET /v1/runs/{run_id}/export`. See bench [SHOWCASE_DEVELOPER.md](../../services/bench/docs/SHOWCASE_DEVELOPER.md) and `showcase/` from `mesocosm init`.

---

## `mesocosm register`

**Summary:** Legacy: register `domain.py` with `DOMAIN_CONFIG` (prefer `env submit` for new repos).

| Parameter | Required | Description |
| --- | --- | --- |
| `domain_file` | Yes | Positional path to `domain.py` (must exist or end with `.py` for dispatch). |
| `--auto-id` | No | Set domain id to parent directory name. |
| `--publish` | No | Publish domain after register. |
| `--bench-url` | No | Global parent flag; bench-api URL for register/publish API. |

---

## `mesocosm doctor`

**Summary:** Probe bench-api health/openapi; with `--local`, also probe env adapter.

| Parameter | Required | Description |
| --- | --- | --- |
| `--base-url` | No | bench-api URL (env: `MESOCOSM_BASE_URL`). Default prod `https://api.swecc.org/bench` or local when `MESOCOSM_LOCAL=1`. |
| `--local` | No | Enable local profile: check adapter at `MESOCOSM_ENV_URL` / default `:8765` and bench-api at `:8010`. Same effect as `MESOCOSM_LOCAL=1` for URL defaults. |

**Exit code:** `0` if checks pass, `1` otherwise. Prints JSON with `issues` and hints (e.g. missing `/bench` prefix on prod).

---

## `mesocosm validate`

**Summary:** Validate a domain registration JSON body against bundled policy (offline).

| Parameter | Required | Description |
| --- | --- | --- |
| `FILE` | Yes | Path to JSON file, or `-` to read stdin. Expected shape: POST `/v1/domains` body. |
| `--base-url` | No | Declared on Typer root but unused by validate (no HTTP). |

**Exit code:** `0` if `ok` in result JSON, else `1`. Policy files live in `swecc_mesocosm/policy/`.

---

## `mesocosm eval test`

**Summary:** Run one dev test episode (`POST /v1/test/episode`).

| Parameter | Required | Description |
| --- | --- | --- |
| `--domain-id` | Yes | Target domain id. |
| `--vow-version` | No | Binding vow version; if omitted, read from domain record `binding_vow.version`. |
| `--model` | Yes | Model id (e.g. `openai/gpt-4o-mini`). |
| `--env-url` | No | Override environment HTTP URL for this episode. |
| `--seed` | No | Episode seed integer. |
| `--temperature` | No | Agent temperature (default: `0.0`). |
| `--max-tokens` | No | Max tokens (default: `4096`). |
| `--base-url` | No | bench-api base URL. |

**Exit:** Non-zero if episode status is `failed`, `cancelled`, or `error`.

---

## `mesocosm eval run`

**Summary:** Create a multi-episode run with aggregation (`POST /v1/runs`).

| Parameter | Required | Description |
| --- | --- | --- |
| `--domain-id` | Yes | Target domain id. |
| `--vow-version` | No | Binding vow version; default from domain record if omitted. |
| `--model` | Yes | Model id. |
| `--num-episodes` | No | Episode count (default: `1`). |
| `--seed-set` | No | JSON array of integers, e.g. `'[1,2,3]'`. |
| `--temperature` | No | Agent temperature (default: `0.0`). |
| `--max-tokens` | No | Max tokens (default: `4096`). |
| `--max-parallel` | No | Parallel episode cap (default: `1`). |
| `--require-published` / `--allow-draft` | No | Default rejects non-`published` domains; draft allowed with `--allow-draft`. |
| `--base-url` | No | bench-api base URL. |

---

## `mesocosm run get`

**Summary:** Fetch run status, episodes, and aggregate scores.

| Parameter | Required | Description |
| --- | --- | --- |
| `RUN_ID` | Yes | Positional platform run id. |
| `--base-url` | No | bench-api base URL. |

**API:** `GET /v1/runs/{id}` plus episode list; prints combined JSON.

---

## `mesocosm run episodes`

**Summary:** List episodes for a run; optionally include traces.

| Parameter | Required | Description |
| --- | --- | --- |
| `RUN_ID` | Yes | Positional platform run id. |
| `--traces` | No | Also fetch run traces (`GET .../traces`) keyed by episode. |
| `--base-url` | No | bench-api base URL. |

---

## Sources

| File | Role |
| --- | --- |
| `swecc_mesocosm/help_text.py` | `mesocosm --help` / `mesocosm run --help` text |
| `swecc_mesocosm/cli.py` | Typer: `doctor`, `validate`, `eval`, `run get`, `run episodes` |
| `bench_common/cli/main.py` | argparse: `auth`, `team`, `env`, `init`, `register`, `run create`, `local`, `export` |
| `swecc_mesocosm/urls.py` | URL defaults and env var precedence |
| `bench_common/auth/session.py` | `SWECC_BENCH_TOKEN` / guest token behavior |
