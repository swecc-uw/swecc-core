from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_policy_dir() -> Path:
    return Path(__file__).resolve().parent / "policy"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MESOCOSM_",
        env_file=".env",
        extra="ignore",
    )

    base_url: str = Field(
        default="http://127.0.0.1:8010",
        description="bench API base URL",
    )
    request_timeout_s: float = 120.0
    policy_dir: Path = Field(default_factory=_default_policy_dir)


settings = Settings()
