from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Storage backend (ORCH_DB_BACKEND).
    # "django" (default): Django ORM against shared swecc Postgres (bench-api in Docker).
    # "sqlite": aiosqlite local file for dev/tests without Postgres (ORCH_SQLITE_PATH).
    db_backend: Literal["django", "sqlite"] = "django"
    sqlite_path: str = "./bench_dev.db"

    # Postgres connection: DB_* from server_env via app/django_settings.py (not ORCH_*).

    # Trace storage — local directory
    trace_dir: str = "./data/traces"

    # LiteLLM — can point at local Ollama, OpenAI, Anthropic, etc.
    # If empty, direct litellm calls are made (uses env vars like OPENAI_API_KEY)
    litellm_proxy_url: str = ""

    # Quotas
    max_parallel_episodes: int = 10
    max_episodes_per_run: int = 1000

    # Sandbox — where cloned envs run (overridden to http://sandbox:8001 in Docker)
    sandbox_url: str = "http://localhost:8001"

    # Canonical model set for "full bench" runs (exactly 5 models).
    # NOTE: Google AI Studio is served by LiteLLM under the `gemini/` prefix
    # (using GEMINI_API_KEY / GOOGLE_API_KEY). The `google/` prefix is NOT a
    # valid LiteLLM provider — use `vertex_ai/` for Vertex AI instead.
    supported_models: list[str] = [
        "anthropic/claude-sonnet-4-6",
        "openai/gpt-4o",
        "gemini/gemini-2.5-flash",
        "deepseek/deepseek-chat",
        "xai/grok-2",
    ]
    # Extra models accepted for user-supplied single-run requests.
    accepted_model_aliases: list[str] = [
        "gemini/gemini-2.5-flash-lite",
        "gemini/gemini-flash-latest",
        "gemini/gemini-flash-lite-latest",
        "gemini/gemini-2.0-flash",
    ]

    # EC2 worker — public API URL the worker uses to poll for bench jobs
    worker_api_url: str = ""

    # Full bench — episodes per model when running a full 5-model bench
    full_bench_episodes_per_model: int = 5

    model_config = SettingsConfigDict(
        env_prefix="ORCH_",
        extra="ignore",
    )


settings = Settings()
