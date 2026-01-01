from pydantic import BaseModel


class Settings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8004

    cors_origins: list[str] = [
        "http://localhost:8000",
        "http://localhost:80",
        "http://localhost:3000",
        "http://api.swecc.org",
    ]


settings = Settings()
