import os

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    jwt_secret_key: str = Field(
        default_factory=lambda: os.getenv("JWT_SECRET", "dev_secret_key_change_in_production")
    )
    jwt_algorithm: str = "HS256"

    db_host: str = Field(default_factory=lambda: os.getenv("DB_HOST", "swecc-db-instance"))
    db_port: int = Field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    db_name: str = Field(default_factory=lambda: os.getenv("DB_NAME", "swecc"))
    db_user: str = Field(default_factory=lambda: os.getenv("DB_USER", "swecc"))
    db_password: str = Field(default_factory=lambda: os.getenv("DB_PASSWORD", "swecc"))

    host: str = "0.0.0.0"
    port: int = 8004

    redis_host: str = Field(default_factory=lambda: os.getenv("REDIS_HOST", "swecc-redis-instance"))
    redis_port: int = Field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))

    cors_origins: list[str] = [
        "http://localhost:8000",
        "http://localhost:80",
        "http://localhost:3000",
        "http://api.swecc.org",
    ]


settings = Settings()
