import os
from urllib.parse import urlparse

from bench_common.model_catalog import EXTRA_MODEL_ALIASES, FULL_BENCH_MODELS
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Gateway path prefix (e.g. when SWAG exposes bench-api under a subpath and strips
    # it before proxying). Used for FastAPI root_path / Swagger OpenAPI URL. Empty when
    # hitting the service directly (local :8010). Set ORCH_GATEWAY_PREFIX or
    # ORCH_PUBLIC_BASE_URL (path component is used if prefix is unset).
    gateway_prefix: str = ""
    public_base_url: str = ""

    # Postgres: DB_* from server_env via app/django_settings.py (Django ORM / Supabase).

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
    supported_models: list[str] = list(FULL_BENCH_MODELS)
    # Extra models accepted for user-supplied single-run requests.
    accepted_model_aliases: list[str] = list(EXTRA_MODEL_ALIASES)

    # EC2 worker — public API URL the worker uses to poll for bench jobs
    worker_api_url: str = ""

    # Full bench — episodes per model when running a full 5-model bench
    full_bench_episodes_per_model: int = 5

    # Auth — guest demo runs (comma-separated domain IDs; empty = all domains allowed)
    guest_runs_per_day: int = 5
    demo_domain_ids: list[str] = []

    model_config = SettingsConfigDict(
        env_prefix="ORCH_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _parse_demo_domains(self) -> "Settings":
        raw = os.environ.get("ORCH_DEMO_DOMAIN_IDS", "")
        if raw.strip():
            object.__setattr__(
                self,
                "demo_domain_ids",
                [x.strip() for x in raw.split(",") if x.strip()],
            )
        return self

    @model_validator(mode="after")
    def _resolve_gateway_prefix(self) -> "Settings":
        prefix = (self.gateway_prefix or "").strip().rstrip("/")
        if not prefix and self.public_base_url:
            path = urlparse(self.public_base_url.strip()).path.rstrip("/")
            prefix = path
        object.__setattr__(self, "gateway_prefix", prefix)
        return self


settings = Settings()
