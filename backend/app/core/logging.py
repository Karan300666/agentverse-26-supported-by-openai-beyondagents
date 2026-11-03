"""Logfire setup: traces for FastAPI requests, SQL queries, and (later) the agent graph."""

import logfire
from fastapi import FastAPI

from app.core.config import get_settings


def setup_logging(app: FastAPI) -> None:
    settings = get_settings()
    token = settings.logfire_token.get_secret_value() if settings.logfire_token else None
    logfire.configure(
        token=get_settings().logfire_token.get_secret_value() if get_settings().logfire_token else None,
        service_name="hospital-voice-agent",
        environment=settings.environment,
        send_to_logfire="if-token-present",
    )
    logfire.instrument_fastapi(app)

    from app.db.session import engine  # imported here to avoid circular imports

    