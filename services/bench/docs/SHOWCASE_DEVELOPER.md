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

mesocosm auth login --username YOU
mesocosm env submit --name "My env" --github-url https://github.com/you/my-bench-env

# After onboarding is ready, note domain_id from Mesocosm developer page or env list
mesocosm run create \
  --domain DOMAIN_UUID \
  --vow-version 1.0.0 \
  --model gemini/gemini-2.0-flash \
  --episodes 1 \
  --visibility gallery_public

# When status is completed:
mesocosm run export RUN_ID -o showcase/data/replay.json
```

Commit `showcase/data/replay.json` (or fetch live from the API) and wire your frontend to `replay[episodeId][turn].reasoning`.

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
