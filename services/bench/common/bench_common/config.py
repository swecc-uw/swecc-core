from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database — bench uses Django ORM against the swecc Postgres DB. Connection
    # settings come from DB_HOST / DB_NAME / DB_USER / DB_PASSWORD / DB_PORT
    # (read directly by app/django_settings.py), not from this Settings class.

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

    # Supported model allowlist (LiteLLM provider/model format)
    supported_models: list[str] = [
        "anthropic/claude-sonnet-4-6",
        "openai/gpt-4o",
        "google/gemini-2.0-flash",
        "deepseek/deepseek-chat",
        "xai/grok-2",
    ]

    # EC2 worker — public API URL the worker uses to poll for bench jobs
    worker_api_url: str = ""

    # Full bench — episodes per model when running a full 5-model bench
    full_bench_episodes_per_model: int = 5

    model_config = {"env_prefix": "ORCH_"}


settings = Settings()
