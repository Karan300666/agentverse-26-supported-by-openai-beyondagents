"""Test setup. Tests use the main database, but every test runs inside one transaction
that is rolled back at the end, so nothing a test writes is ever saved."""

import os

os.environ["LOGFIRE_TOKEN"] = ""  

import logfire  
import pytest 
import pytest_asyncio 
from sqlalchemy import text 
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine 
from sqlalchemy.pool import NullPool 

logfire.configure(send_to_logfire=False, console=False)

from app.core.config import get_settings 
from app.voice import confirmations 
from app.voice import session as voice_session 


@pytest_asyncio.fixture
async def db():
    """A session whose commits are savepoints inside one outer transaction.
    The outer transaction is always rolled back, so the real data is never changed."""
    engine = create_async_engine(
        get_settings().async_database_url,
        poolclass=NullPool,
        connect_args={"ssl": True, "statement_cache_size": 0},
    )
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            # Pin the slot length for the tests (undone by the final rollback).
            await session.execute(
                text(
                    "INSERT INTO hospital_settings (key, value) "
                    "VALUES ('appointment_slot_minutes', '20') "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
                )
            )
            await session.commit()
            yield session
        finally:
            await session.close()
            await outer.rollback()
    await engine.dispose()


@pytest.fixture(autouse=True)
def reset_voice_state():
    voice_session._sessions.clear()
    confirmations._pending.clear()
    yield
    voice_session._sessions.clear()
    confirmations._pending.clear()


class FakeClock:
    """Replaces the `time` module inside the voice modules so tests can move time forward."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(voice_session, "time", fake)
    monkeypatch.setattr(confirmations, "time", fake)
    return fake


@pytest.fixture
def limits(monkeypatch):
    """Pin the limits so tests don't depend on the values in .env."""
    settings = get_settings()
    monkeypatch.setattr(settings, "max_tool_calls_per_minute", 3)
    monkeypatch.setattr(settings, "max_tool_calls_per_session", 5)
    monkeypatch.setattr(settings, "max_concurrent_sessions_per_patient", 1)
    monkeypatch.setattr(settings, "session_max_minutes", 30)
    return settings