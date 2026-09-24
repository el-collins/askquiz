import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    database_url: str
    daily_request_cap: int


def load_settings() -> Settings:
    groq_api_key = os.environ.get("GROQ_API_KEY")
    database_url = os.environ.get("DATABASE_URL")
    if not groq_api_key:
        raise RuntimeError("Missing required environment variable: GROQ_API_KEY")
    if not database_url:
        raise RuntimeError("Missing required environment variable: DATABASE_URL")
    daily_request_cap = int(os.environ.get("DAILY_REQUEST_CAP", "50"))
    return Settings(
        groq_api_key=groq_api_key,
        database_url=database_url,
        daily_request_cap=daily_request_cap,
    )
