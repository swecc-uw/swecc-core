# mesocosm CLI commands

Reference for `mesocosm` on the **cli-updates** branch. Descriptions are capped at 12 words.

**Global (bench_common commands):** `--bench-url` — bench-api base URL (default from env/credentials).

**Global (Typer commands):** `--base-url` / `MESOCOSM_BASE_URL` — same role for `doctor`, `validate`, `eval`, `run get|episodes`.

| Command | Arguments / flags | Description |
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
| `run local` | `--manifest`; `--domain-id`; `--model`; `--env-url`; `--episodes`; `--seeds`; `--system-prompt`; `--temperature`; `--max-tokens`; `--parallel`; `--quiet` | Bench locally with Ollama and benchanything.json |
| `env submit` | `--name`; `--github-url`; `--description`; `--team`; `--solo` | Submit GitHub repo as developer environment |
| `env list` | `--team`; `--solo` | List your developer environments |
| `run create` | `--domain`; `--vow-version`; `--model`; `--episodes`; `--parallel`; `--system-prompt`; `--temperature`; `--max-tokens`; `--team`; `--solo`; `--visibility`; `--env-id` | Start platform bench run via API |
| `run export` | `RUN_ID`; `-o` / `--output` | Download run JSON for showcase or replay |
| `register` | `domain.py`; `--auto-id`; `--publish` | Legacy register domain.py; prefer env submit |
| `doctor` | `--base-url`; `--local` | Check bench-api reachability; local checks adapter |
| `validate` | `FILE` or `-` | Validate domain JSON against policy constraints |
| `eval test` | `--domain-id`; `--vow-version`; `--model`; `--env-url`; `--seed`; `--temperature`; `--max-tokens`; `--base-url` | Run single test episode via bench-api |
| `eval run` | `--domain-id`; `--vow-version`; `--model`; `--num-episodes`; `--seed-set`; `--temperature`; `--max-tokens`; `--max-parallel`; `--require-published` / `--allow-draft`; `--base-url` | Run multi-episode eval with scoring aggregation |
| `run get` | `RUN_ID`; `--base-url` | Fetch run status and aggregate scores |
| `run episodes` | `RUN_ID`; `--traces`; `--base-url` | List episodes for a run; optional traces |

**Sources:** `swecc_mesocosm/help_text.py`, `swecc_mesocosm/cli.py`, `bench_common/cli/main.py`.

**Related:** workflow overview in [README.md](./README.md); packaging/routing in [PACKAGING.md](./PACKAGING.md).
