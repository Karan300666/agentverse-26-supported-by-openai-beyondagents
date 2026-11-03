"""Application settings, loaded from environment variables / the repo-root .env file."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

from pydantic import SecretStr

# backend/app/core/config.py -> backend directory is the project root for .env
ROOT_DIR = Path(__file__).resolve().parents[2]

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
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Hospital Voice Agent"
    environment: str = "development"
    debug: bool = False
    database_url: str
    logfire_token: SecretStr | None = None
    openai_api_key: SecretStr
    guard_model: str = "gpt-4o-mini"

    @property
    def async_database_url(self) -> str:
        return to_asyncpg_url(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()