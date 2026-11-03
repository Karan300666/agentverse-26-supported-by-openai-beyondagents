"""Shared OpenAI client, traced by Logfire."""

from functools import lru_cache

import logfire
from openai import AsyncOpenAI

from app.core.config import get_settings


@lru_cache
def get_openai_client() -> AsyncOpenAI:
    client = AsyncOpenAI(api_key=get_settings().openai_api_key.get_secret_value())
    logfire.instrument_openai(client)
    return client