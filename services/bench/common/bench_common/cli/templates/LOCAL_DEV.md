# Local development (Ollama)

Iterate on `env.py` and `benchanything.json` on your machine before `bench env submit`. No API keys, no cloud setup — only [Ollama](https://ollama.com).

## One-time setup

1. Install the CLI: `pip install swecc-mesocosm` (provides the `bench` command)
2. Install Ollama and pull a model:
   ```bash
   ollama pull llama3.2
   ```
3. Ensure Ollama is running (`ollama serve` — the desktop app usually does this).

## Dev loop

**Terminal 1 — env server**

```bash
python adapter.py
# → http://localhost:8765/health
```

**Terminal 2 — bench episodes**

```bash
bench run local
# same as: bench run local --model ollama/llama3.2
```

Uses `benchanything.json` for the binding vow and scoring. Does **not** register the domain or create platform runs.

## Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--model` | `ollama/llama3.2` | Must be `ollama/<name>` matching a pulled model |
| `--episodes` | `5` | Number of episodes |
| `--env-url` | `http://localhost:8765` | Adapter URL if you changed the port |
| `--manifest` | `benchanything.json` | Alternate manifest path |
| `--system-prompt` | — | Extra instruction for the agent |

## Troubleshooting

- **`Connection refused` to Ollama** — start Ollama / run `ollama serve`.
- **Model not found** — `ollama list` and use `ollama/<exact-name>` (e.g. `ollama/llama3.2`).
- **Adapter not reachable** — start `python adapter.py` first; check `--env-url`.

## Ship to Mesocosm

When local runs look good:

```bash
bench auth login --username YOU --password PASS
bench env submit --name "My env" --github-url https://github.com/you/your-repo
bench run create --domain DOMAIN_ID --vow-version 1.0.0 --model gemini/gemini-2.0-flash ...
```

Platform runs use cloud models on SWECC infrastructure; local Ollama is only for your machine.
