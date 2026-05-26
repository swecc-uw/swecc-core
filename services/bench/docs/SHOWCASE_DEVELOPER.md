# Showcase in **your** repo (not Mesocosm)

Mesocosm’s `/showcase/*` pages are **curated marketing** with hand-built animations. For environment authors, the intended path is:

1. Implement `benchanything.json` + `adapter.py` + `env.py` in **your GitHub repo**
2. Submit via `bench env submit`
3. Run models with `bench run create`
4. **Export** completed runs to JSON and build **your own** docs site / README demo around that file

The platform stores step traces including **`reasoning`** — the model’s text output for each step (not full prompt/response dumps).

## Quick start

```bash
pip install swecc-mesocosm   # provides `bench` and `mesocosm` CLIs

mkdir my-bench-env && cd my-bench-env
bench init

# edit env.py, benchanything.json, then iterate locally with Ollama (no submit):
#   ollama pull llama3.2 && python adapter.py
#   bench run local
# See LOCAL_DEV.md in your repo after `bench init`.

bench auth login --username YOU --password PASS
bench env submit --name "My env" --github-url https://github.com/you/my-bench-env

# After onboarding is ready, note domain_id from Mesocosm developer page or env list
bench run create \
  --domain DOMAIN_UUID \
  --vow-version 1.0.0 \
  --model gemini/gemini-2.0-flash \
  --episodes 1 \
  --visibility gallery_public

# When status is completed:
bench run export RUN_ID -o showcase/data/replay.json
```

Commit `showcase/data/replay.json` (or fetch live from the API) and wire your frontend to `replay[episodeId][turn].reasoning`.

## Export API

```http
GET /v1/runs/{run_id}/export
```

- **Auth:** Bearer member/guest token, **or** no auth if the run is `gallery_public` and `completed`
- **Response:** `schema_version`, `run`, `episodes`, `traces` (raw events), `replay` (showcase-friendly turns)

### Replay turn shape

```json
{
  "step": 1,
  "observation": { "board": ["A", "B", "C"] },
  "reasoning": "Two signals. Size a core position before CPI.",
  "action": { "guess": ["A", "B", "C", "D"] },
  "reward": 0.0,
  "terminated": false
}
```

Use `reasoning` for prose UI (like Mesocosm trading showcase). Use `observation` / `action` to drive game boards, charts, etc.

## Public replay on Mesocosm

Gallery-public completed runs are readable at:

`/runs/{run_id}`

No account required. Same export payload is loaded in the browser.

## `bench init` files

| File | Purpose |
|------|---------|
| `benchanything.json` | Manifest (binding vow + scoring) |
| `adapter.py` | HTTP server (`serve(MyEnv)`) |
| `env.py` | Your `reset` / `step` logic |
| `requirements.txt` | Optional pip deps for sandbox |
| `showcase/README.md` | This workflow in-repo |
| `showcase/replay.example.json` | Example export shape |

## Tips for showcase-quality envs

- **Multi-step episodes** with rich JSON observations (boards, portfolios, puzzles)
- **Text or JSON action spaces** so `reasoning` reads naturally before parsing
- **`max_steps`** high enough for a story, low enough to cap cost
- **`gallery_public`** on demo runs you want embeddable without login
- **Deterministic seeds** (`seed_set` on run create) for stable replays

## Trace events (raw)

Export also includes full `traces` per episode. Event types include `observation`, `model_call` (reasoning text), `action`, `step_result`, `episode_end`.

Legacy `GET /v1/runs/{id}/traces` remains available; prefer `/export` for new integrations.
