"""Application settings, loaded from environment variables / the repo-root .env file."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend directory contains the app's .env file
BACKEND_DIR = Path(__file__).resolve().parents[2]

# libpq-only query params that asyncpg does not understand
_UNSUPPORTED_QUERY_PARAMS = {"sslmode", "channel_binding"}


def to_asyncpg_url(url: str) -> str:
    """Convert a standard Postgres URL (e.g. from Neon) into a SQLAlchemy asyncpg URL."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in _UNSUPPORTED_QUERY_PARAMS]
    return urlunsplit(
        ("postgresql+asyncpg", parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Clinora"
    environment: str = "development"
    debug: bool = False

    database_url: str  # required
    logfire_token: SecretStr | None = None

    openai_api_key: SecretStr

    realtime_model: str
    realtime_transcription_model: str | None = None
    realtime_voice: str | None = None

    cors_origins: list[str] = []

    @property
    def async_database_url(self) -> str:
        return to_asyncpg_url(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()