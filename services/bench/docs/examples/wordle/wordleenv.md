How I (Zero to Little experience in coding python by myself) coded a Wordle Env by myself

This guide does two things at once:
1. It documents how I (a near-beginner) walked through building the Wordle environment.
2. It's written so that anyone building ANY environment for this platform can follow along — I'll call out the "for your env" version at each step.

Think of the **Wordle-specific** parts as the worked example, and the **general** parts as the template you'd copy for a trivia env, a maze env, a negotiation env, whatever.

---

Step 1: Create `env.py`, `domain.py`, `adapter.py`

These three files are the minimum an env needs:
- `env.py` — the actual game logic (reset the world, take an action, return a reward).
- `domain.py` — the "contract" — tells the platform what observations, actions, and rewards look like.
- `adapter.py` — a tiny file (like 5 lines) that starts an HTTP server so the platform can talk to your env.

Optional 4th file:
- `register.py` — pushes your domain config to the platform's API. Only needed when you want to actually use the leaderboard. You can do this with a curl command instead if you want.

**For your env:** same three files, same names. The pattern is identical no matter what you're building. Just put them in `docs/examples/<your-env-name>/` (or anywhere you like).

---

Step 2: Import `BaseEnv` and `StepResult` from `src.env_sdk.base`. I also added the entire wordle word list, called `words.txt`.

At the top of `env.py`:

```python
from __future__ import annotations
import random
from typing import Any

from bench_common.env_sdk.base import BaseEnv, StepResult
```

- `BaseEnv` is the abstract class every env subclasses. It forces you to implement `reset()` and `step()`.
- `StepResult` is a dataclass — it's what `step()` has to return. Five fields: `observation`, `reward`, `terminated`, `truncated`, `info`.

For Wordle I also dropped `words.txt` in the same folder — a flat file with one word per line. I load it at reset time.

**For your env:** import the same two things. If your env needs extra data (word lists, maps, questions, puzzles, a dataset), put it next to `env.py` and load it inside `reset()` or in `__init__`. Keep anything that's shared across episodes (like the full word list) loaded once; keep anything that's per-episode (like the secret word) set in `reset()`.

---

Step 3: Create and define your default functions — the constructor, `reset`, and `step`

Every `BaseEnv` subclass needs three things:

### 3a. The class declaration

```python
class WordleEnv(BaseEnv):
    """6 tries to guess a 5-letter word."""
```

One env class per file. It has to subclass `BaseEnv` or the platform won't accept it.

**For your env:** `class MyEnv(BaseEnv):` — same shape.

### 3b. The constructor (`__init__`)

The constructor runs once, when the env instance is created. Put anything here that should exist for the whole lifetime of a single episode but not persist across episodes (the platform spins up a fresh env instance per episode — I didn't know this at first).

For Wordle I needed:
- `self._secret`: the secret word (set in reset, not init, because it depends on the seed).
- `self._guesses_used`: counter, starts at 0.
- `self._max_guesses`: the rule — 6 guesses.
- `self._valid_words`: the full word list loaded from `words.txt` — load this once here so I don't re-read the file every `reset()`.
- `self._rng`: a `random.Random()` instance so seeded resets are deterministic.

```python
def __init__(self) -> None:
    self._secret: str | None = None
    self._guesses_used: int = 0
    self._max_guesses: int = 6
    self._rng = random.Random()
    # Load the word list once per instance
    with open(os.path.join(os.path.dirname(__file__), "words.txt")) as f:
        self._valid_words = [w.strip().lower() for w in f if w.strip()]
```

Notes I tripped on:
- `__init__` takes `self` — not `(self, something)` unless the platform passes args. It doesn't. Keep it parameterless.
- Don't pick the secret word in `__init__` — pick it in `reset()`, because `reset()` is where the seed arrives.

**For your env:** put constants, data files, and "things that exist for the whole episode" here. Put per-episode random choices in `reset()`.

### 3c. `reset(seed, **params)`

`reset()` is called at the start of every episode. It:
1. Seeds the RNG (for reproducibility — if two runs use the same seed, they should get the same secret word).
2. Picks fresh per-episode state (the secret word, for me).
3. Resets any counters (`self._guesses_used = 0`).
4. Returns the **initial observation** — what the agent gets to see at step 0.

```python
def reset(self, seed: int | None = None, **params: Any) -> dict[str, Any]:
    self._rng.seed(seed)
    self._secret = self._rng.choice(self._valid_words)
    self._guesses_used = 0

    return {
        "instructions": "Guess the 5-letter word. You have 6 tries.",
        "guesses_so_far": [],
        "guesses_remaining": self._max_guesses,
    }
```

Things I got wrong the first time:
- I tried to return the secret word in the observation. DON'T. The agent sees whatever `reset()` returns — so if you leak the answer, the benchmark is meaningless.
- The observation must be JSON-serialisable: dicts, lists, strings, numbers. No Python objects.

**For your env:**
- Seed your RNG here, always (even if you don't use randomness — it costs nothing).
- Return only what the agent should see at step 0. Hide the answer / goal state.
- Clear any counters from a prior episode. Even though the platform makes a fresh instance, I still reset counters defensively — cheap insurance.

### 3d. `step(action)`

`step()` is called once per agent action. It:
1. Takes the agent's action (for Wordle: a 5-letter guess string).
2. Validates it (is it 5 letters? is it in the word list?).
3. Computes the outcome (which letters are green / yellow / gray).
4. Decides if the episode is over (`terminated=True`) and what the reward is.
5. Returns a `StepResult`.

```python
def step(self, action: Any) -> StepResult:
    if self._secret is None:
        raise RuntimeError("Call reset() before step()")

    guess = str(action).strip().lower()
    self._guesses_used += 1

    # Validate
    if len(guess) != 5 or guess not in self._valid_words:
        return StepResult(
            observation={"error": "invalid guess", "guesses_remaining":
                         self._max_guesses - self._guesses_used},
            reward=0.0,
            terminated=False,
            truncated=False,
            info={"valid": "False", "guess": guess},
        )

    # Score the guess letter by letter
    feedback = self._score_guess(guess, self._secret)  # "green"/"yellow"/"gray" per letter
    won = guess == self._secret
    out_of_guesses = self._guesses_used >= self._max_guesses

    reward = 1.0 if won else 0.0   # binary reward — or use a shaped reward (see below)
    terminated = won or out_of_guesses

    return StepResult(
        observation={
            "last_guess": guess,
            "feedback": feedback,
            "guesses_remaining": self._max_guesses - self._guesses_used,
        },
        reward=reward,
        terminated=terminated,
        truncated=False,
        info={
            "won": str(won),
            "guess": guess,
            "secret": self._secret if terminated else "",  # only reveal at the end
            "guesses_used": str(self._guesses_used),
        },
    )
```

Key rules I learned the hard way:
- `info` values MUST be strings. No bools, no ints, no nested dicts. Stringify everything (`str(True)`, `str(42)`). The platform's tracer will choke otherwise.
- `terminated=True` means "the episode ended naturally" (won or out of guesses).
- `truncated=True` means "we ran out of wall-clock time / platform step budget." You usually leave this `False` and let the platform set it.
- Return the `StepResult` by *name* (keyword args) — I kept forgetting the field order.

**For your env:**
- Always check `self._state is None` at the top of `step()` and raise — forces users to call `reset()` first.
- Decide: binary reward (`1.0 / 0.0`), shaped reward (partial credit), or sparse (`0` until the end, then a big payoff)? Wordle works fine binary, but a shaped version ("reward = fraction of green letters") is a nicer learning signal.
- Put useful metrics in `info` — anything you want the leaderboard to score, plus things you want to eyeball in traces ("guess", "guesses_used", etc.).

---

Step 4: Optional — `close()` and `render()`

`BaseEnv` gives you default no-op implementations of these. Override them only if you need to.

- `close()`: release resources (DB connections, sockets, subprocesses). Wordle has none, so I skipped it.
- `render(mode)`: return a human-readable snapshot of the current state. Nice for debugging traces.

```python
def render(self, mode: str = "text") -> str:
    return f"secret={'*' * 5} guesses_used={self._guesses_used}/{self._max_guesses}"
```

**For your env:** skip both unless you specifically need them. `render()` is pure convenience for when you're watching replays.

---

Step 5: Write `domain.py` — the Binding Vow

`domain.py` doesn't touch game logic. It's pure metadata. It tells the platform:

- What observations look like (so the agent can be told what to expect)
- What actions are valid
- How the reward works
- Episode limits (max steps, max seconds)
- Where your env server is running (`ADAPTER_URL`)
- How to score a Run (the leaderboard config)

Copy the structure from `template/domain.py` — it's already laid out with `# ── Edit these ──` markers.

### 5a. Top-of-file constants

```python
DOMAIN_ID   = "wordle"
DOMAIN_NAME = "Wordle"
OWNER_ID    = "your-username"
ADAPTER_URL = "http://localhost:8888"   # wherever adapter.py listens
TAGS        = ["nlp", "word-game", "tier1"]
```

`DOMAIN_ID` is the slug. Must be unique across the platform. `ADAPTER_URL` is whatever port/host your adapter is running on — if you're local, it's `http://localhost:<port>`. If you're hosting it somewhere, put the real URL.

**For your env:** change all five values. Don't reuse IDs — the register call will conflict.

### 5b. The `BINDING_VOW`

This is the contract. For Wordle:

```python
BINDING_VOW = BindingVow(
    id="wordle-v1",
    version="1.0.0",
    domain_id=DOMAIN_ID,
    tier="tier1",
    description=(
        "Classic Wordle. The agent has 6 tries to guess a 5-letter word. "
        "After each guess, it receives per-letter feedback: "
        "'green' (correct letter, correct position), 'yellow' (correct letter, "
        "wrong position), 'gray' (not in the word)."
    ),
    observation_space=SpaceSpec(
        type=SpaceType.JSON,
        description=(
            '{ "last_guess": str | null, '
            '  "feedback": list[str] | null, '
            '  "guesses_remaining": int }'
        ),
    ),
    action_space=SpaceSpec(
        type=SpaceType.TEXT,
        description="A 5-letter lowercase English word from the valid word list.",
    ),
    reward=RewardSpec(
        type="binary",
        range={"low": 0.0, "high": 1.0},
        description="1.0 if the agent guesses the word within 6 tries, else 0.0",
    ),
    episode=EpisodeSemantics(
        max_steps=6,
        supports_seed=True,
        deterministic_reset=True,
    ),
    techniques=[],
)
```

Things to know:
- `type=SpaceType.TEXT` for free-form strings; `SpaceType.DISCRETE` with `enum_values=[...]` for a fixed choice set; `SpaceType.JSON` for structured dicts. The full list is in `src/core/binding_vow.py` — I just grepped that file to find the options.
- `max_steps=6` is the hard cap. If the agent somehow doesn't terminate, the platform cuts it off with `truncated=True`.
- `description` fields end up in the agent's system prompt — write them like you're writing instructions for a smart intern who hasn't read your code.

**For your env:**
- Pick the simplest `SpaceType` that describes what you're actually sending / receiving. Don't over-engineer.
- Always set `max_steps` — agents can loop forever otherwise and eat your API budget.
- Keep `techniques=[]` unless your env genuinely needs one of `tool_calling` / `memory` / `multi_agent`. (Wordle doesn't.)
- Bump `version` every time you change the contract in a way that breaks old runs. Same-domain new-version = a fresh leaderboard.

### 5c. `SCORING`

This tells the leaderboard what to actually measure.

```python
SCORING = ScoringConfig(
    primary_metric="win_rate",
    higher_is_better=True,
    metrics=[
        MetricDef(
            name="win_rate",
            type="terminal_field",
            field="won",                 # set in step() info as "True"/"False"
            aggregation="pass_rate",
        ),
        MetricDef(
            name="avg_guesses",
            type="terminal_field",
            field="guesses_used",        # the smaller the better — but higher_is_better=True
            aggregation="mean",          # so treat this as a secondary, not primary
        ),
        MetricDef(
            name="avg_reward",
            type="episode_reward",
            aggregation="mean",
        ),
    ],
)
```

Important gotchas:
- `terminal_field` reads from `info` on the LAST step. Whatever key you reference here MUST be set by your `step()` method on the terminal step, as a string.
- `pass_rate` counts any non-falsy / non-zero string as a pass. `"True"` passes, `"False"` fails, `"0"` fails, `"1"` passes.
- `episode_reward` is the sum of all step rewards. For binary-reward envs, this is the same as "did they win."
- `primary_metric` is the one the leaderboard ranks by. Pick the metric that most honestly represents success.

**For your env:**
- You need at least one metric. Two is better (a primary success signal + `episode_reward` for sanity).
- If you want a richer score (e.g. "LLM judge rates the output 1–5"), use `type="trajectory_judge"` and a `judge_config` — but that's a Phase 2 feature, skip it for now.

### 5d. The `DOMAIN_CONFIG` wrapper

This just packages up the pieces so `register.py` has one thing to send:

```python
DOMAIN_CONFIG = DomainConfig(
    id=DOMAIN_ID,
    name=DOMAIN_NAME,
    owner_id=OWNER_ID,
    binding_vow=BINDING_VOW,
    endpoint=EnvironmentEndpoint(mode="remote", url=ADAPTER_URL),
    scoring=SCORING,
    tags=TAGS,
)
```

Copy-paste this exactly; only the variable names you filled in at the top of the file matter.

**For your env:** same block, unchanged.

---

Step 6: Write `adapter.py` — the HTTP server

The adapter is tiny. The platform needs your env to speak HTTP on four endpoints (`/reset`, `/step`, `/close`, `/health`) — the `serve()` helper does all of that automatically. All `adapter.py` does is point `serve()` at your `env.py` class.

```python
import argparse
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from docs.examples.wordle.env import WordleEnv
from bench_common.env_sdk import serve

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WordleEnv adapter server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8888)
    args = parser.parse_args()

    print(f"Starting WordleEnv adapter on http://{args.host}:{args.port}")
    serve(WordleEnv, host=args.host, port=args.port)
```

What's happening:
- The `sys.path.insert(...)` line lets this file find the `src/` package when you run it from anywhere. It walks up three directories (`../../..`) because this file is three folders deep (`docs/examples/wordle/`). If you put your env somewhere else, count the depth and adjust.
- `serve(WordleEnv, ...)` spins up FastAPI on the given port and registers `/reset` / `/step` / `/close` / `/render` / `/health`, all wired up to a fresh `WordleEnv()` instance per episode.
- The port HAS to match `ADAPTER_URL` in `domain.py`. I set both to `8888`.

**For your env:**
- Change the import (`from docs.examples.<your-env>.env import YourEnv`).
- Pick a port. Any port. Just make sure `ADAPTER_URL` in `domain.py` matches.
- Don't hand-roll HTTP. `serve()` is there so you don't have to.

---

Step 7: (Optional) Write `register.py`

Only needed if you want to push your domain into the platform's DB (required for leaderboard submissions). You can skip this while you're still iterating — the `uv run python -m src.inference.bench` command works without it.

```python
import argparse
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from docs.examples.wordle.domain import DOMAIN_CONFIG, DOMAIN_ID
from bench_common.env_sdk.registration import publish_domain, register_domain

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Register WordleEnv")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--publish", action="store_true",
                        help="Freeze the Binding Vow and enable leaderboard submissions")
    args = parser.parse_args()

    register_domain(DOMAIN_CONFIG, api_url=args.api)
    if args.publish:
        publish_domain(DOMAIN_ID, api_url=args.api)
```

- First run (without `--publish`): creates the domain as a **draft**. You can still edit `domain.py` and re-run to update it.
- Once you're happy with the Binding Vow, re-run with `--publish` to freeze it. Published domains can't be edited (that's the whole point of versioning — old scores stay meaningful).

**For your env:** change the import paths (`<your-env>` slug), otherwise identical. If you update `domain.py` while still in draft, just re-run without `--publish` and it will PATCH the existing entry.

---

Step 8: Running everything end-to-end

Three terminals, in order:

**Terminal 1 — platform API (only needed if you're using register.py / leaderboard):**
```
uv run uvicorn src.api.app:app --reload
```

**Terminal 2 — your env adapter:**
```
uv run python docs/examples/wordle/adapter.py --port 8888
```
Test it:
```
curl http://localhost:8888/health
```
You should see `{"status":"ok","env":"WordleEnv","episodes":0}`.

**Terminal 3 — register the domain, then bench a model:**
```
uv run python docs/examples/wordle/register.py
uv run python -m src.inference.bench \
    --model ollama/llama3.2 \
    --domain wordle \
    --env-url http://localhost:8888 \
    --episodes 10
```

If your env server is reachable and your `domain.py` matches the platform's expectations, you'll see scores print out. If not, the most common failures are:
- `ADAPTER_URL` in `domain.py` doesn't match the port the adapter is actually listening on
- `info` dict has a non-string value somewhere — trace writer crashes
- The agent's action isn't in the action space you declared — you'll get a validation failure at step time

---

Step 9: Pre-flight checklist before publishing (from the docs/README)

Before you call `register.py --publish`, tick off each of these:

- [ ] `reset(seed=42)` twice returns the SAME initial observation (deterministic)
- [ ] `step()` eventually returns `terminated=True` — you can't loop forever
- [ ] Every value in `info` is a string, not a bool/int/dict
- [ ] `binding_vow.episode.max_steps` is set (prevents runaway episodes)
- [ ] At least one `MetricDef` of type `terminal_field` or `episode_reward` exists
- [ ] `uv run python -m src.inference.bench --domain <id> ...` returns results without errors

Once all six check out, publish with `--publish`. After that, the Binding Vow is frozen for this version — any future changes need a new `version` string.

---

## Common pitfalls I hit (and how to fix them)

- **"Call reset() before step()" errors in traces** — your state variable (`self._secret`, `self._question`, whatever) is `None`. The platform always calls `/reset` before `/step`, so this usually means `reset()` forgot to set the state, or `__init__` is resetting it back to None after `reset()` ran.

- **`info` keys missing from the leaderboard** — the key is there, but the value isn't a string. `str(True)` not `True`. Same for numbers.

- **Same seed, different answer** — you forgot to call `self._rng.seed(seed)` inside `reset()`. The platform passes seed as a keyword arg — make sure your signature is `def reset(self, seed=None, **params)`.

- **Adapter server starts but the platform gets 404** — the adapter uses `/reset`, `/step`, etc. (no versioning). Don't accidentally mount them under a prefix.

- **"Domain already exists" error** — `register.py` already tries to PATCH draft domains. If the domain is already `published`, you can't edit it; bump `binding_vow.version` to create a new version instead.

- **Seed is ignored** — the agent's LLM call is seeded separately from the env. Even with deterministic reset, model non-determinism (temperature > 0, sampling) can still vary scores. Set `temperature=0` in your `AgentConfig` for reproducible comparisons.

---

## File-by-file summary (generalized)

```
docs/examples/<your-env>/
├── env.py          # BaseEnv subclass: __init__, reset, step (+ optional close/render)
├── domain.py       # Constants, BindingVow, ScoringConfig, DomainConfig
├── adapter.py      # ~15 lines: serve(YourEnv, port=NNNN)
├── register.py     # ~15 lines: register_domain(config) [+ --publish]
└── <data files>    # Optional: word lists, question banks, maps, etc.
```

That's the whole recipe. Same four files for Wordle, same four files for a trivia quiz, same four files for a browser agent env. What changes between envs is:
1. The logic inside `env.py` (obviously)
2. The `BindingVow` shape in `domain.py` (text vs. JSON vs. image observations)
3. The `MetricDef`s in `ScoringConfig` (what "success" means for your env)

If you've got this far, you have a working env. The hardest parts for me were (a) realizing `info` values must all be strings, and (b) understanding that the `BindingVow` isn't enforcement — it's documentation for the agent. The platform trusts what you send; it just hands your shape description to the LLM so the agent knows the rules.
