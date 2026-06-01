# Repo showcase (your frontend)

Build a marketing or demo UI **in this repository** that replays a real bench run from Mesocosm.

## Workflow

1. Submit this repo: `mesocosm env submit --name "..." --github-url https://github.com/you/your-repo`
2. Wait for `ready`, then bench a model:
   ```bash
   mesocosm run create --domain YOUR_DOMAIN_ID --vow-version 1.0.0 --model gemini/gemini-3.1-flash-lite --episodes 1 --visibility gallery_public
   ```
3. **Watch live status** (after create returns a run id):
   ```bash
   mesocosm run watch RUN_ID
   ```
   Or open the bundled UI:
   ```bash
   cd showcase && python -m http.server 8080
   # http://localhost:8080/?run_id=RUN_ID&api=https://api.swecc.org/bench
   ```
4. Export the run (after it completes):
   ```bash
   mesocosm run export RUN_ID -o showcase/data/replay.json
   ```
5. Point your frontend at `replay.json`. Each turn includes:
   - `observation` — env state for your UI
   - `reasoning` — model text (what the agent said before acting)
   - `action` — parsed action sent to the env
   - `reward`, `terminated`, etc.

Public runs (`gallery_public` + completed) can also be viewed at:

`https://mesocosm…/runs/RUN_ID` (no login).

## Live status UI

`index.html` polls `GET /v1/runs/status` and shows:

- `status_reason` — why a run failed or was cancelled
- `status_detail` — episode outcome counts and top failure/truncation reasons
- Per-episode `terminal_info.reason` (step limit, token budget, etc.)

Pass `?run_id=…&api=…` in the URL or fill the form. Optional bearer token for private runs.

## `replay.json` shape

See `replay.example.json`. Use `replay[episode_id][i].reasoning` for showcase-style prose alongside observations and actions.
