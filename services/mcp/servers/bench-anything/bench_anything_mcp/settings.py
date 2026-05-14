from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_rules_dir() -> Path:
    return Path(__file__).resolve().parent / "rules"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BENCH_ANYTHING_",
        env_file=".env",
        extra="ignore",
    )

    base_url: str = Field(default="http://127.0.0.1:8000", description="BenchAnything API base URL")
    request_timeout_s: float = 120.0
    rules_dir: Path = Field(default_factory=_default_rules_dir)


settings = Settings()
