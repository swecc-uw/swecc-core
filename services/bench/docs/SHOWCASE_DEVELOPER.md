# Showcase in **your** repo (not Mesocosm)

Mesocosm’s `/showcase/*` pages are **curated marketing** with hand-built animations. For environment authors, the intended path is:

1. Implement `benchanything.json` + `adapter.py` + `env.py` in **your GitHub repo**
2. Submit via `mesocosm env submit`
3. Run models with `mesocosm run create`
4. **Export** completed runs to JSON and build **your own** docs site / README demo around that file

The platform stores step traces including **`reasoning`** — the model’s text output for each step (not full prompt/response dumps).

## Quick start

```bash
pip install swecc-mesocosm

mkdir my-bench-env && cd my-bench-env
mesocosm init

# edit env.py, benchanything.json, then iterate locally with Ollama (no submit):
#   ollama pull llama3.2 && python adapter.py
#   mesocosm run local
# See LOCAL_DEV.md in your repo after `mesocosm init`.

mesocosm auth login
mesocosm env submit --name "My env" --github-url https://github.com/you/my-bench-env

# After onboarding is ready, note domain_id from Mesocosm developer page or env list
mesocosm run create \
  --domain DOMAIN_UUID \
  --vow-version 1.0.0 \
  --model gemini/gemini-3.1-flash-lite \
  --episodes 1
# Member runs default to gallery_public; use --visibility private to opt out.

# When status is completed:
mesocosm run export RUN_ID -o showcase/data/replay.json
```

Commit `showcase/data/replay.json` (or fetch live from the API) and wire your frontend to `replay[episodeId][turn].reasoning`.

## Run visibility

| Surface | Default | Notes |
| --- | --- | --- |
| `POST /v1/runs` (member) | `gallery_public` | Pass `"visibility": "private"` in the body to keep off the gallery. |
| `POST /v1/runs` (guest) | `gallery_public` | Guest runs expire after 7 days. |
| `POST /v1/test/episode` (dev smoke) | `private` | Internal dev harness only; not promoted to the gallery. |
| `mesocosm run create` | `gallery_public` | CLI `--visibility private` opts out. |

Public completed runs appear on `GET /v1/gallery/runs` and domain gallery endpoints; private runs show only in the caller's mine lists (`GET /v1/runs`, `GET /v1/domains/{id}/runs/mine`).

## Export API

```http
GET /v1/runs/{run_id}/export
```

- **Auth:** Bearer member/guest token, **or** no auth if the run is `gallery_public` and `completed`
- **Response:** `schema_version`, `run`, `episodes`, `traces` (raw events), `replay` (showcase-friendly turns)

### Replay turn shape

See prior docs / `replay.example.json` from `mesocosm init`.

## `mesocosm init` files

| File | Role |
|------|------|
| `benchanything.json` | Manifest (binding vow + scoring) |
| `adapter.py` | HTTP server (`serve(MyEnv)`) |
| `env.py` | Your `BaseEnv` logic |
| `showcase/` | Optional demo UI + `replay.json` |
