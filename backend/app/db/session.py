"""Async SQLAlchemy engine and session dependency."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.async_database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    # Neon requires SSL. The statement cache is disabled so Neon's pooled
    # (PgBouncer) endpoint works with asyncpg.
    connect_args={"ssl": True, "statement_cache_size": 0},
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with AsyncSessionLocal() as session:
        yield session


# Reusable typed dependency: write `db: DbSession` in any route.
DbSession = Annotated[AsyncSession, Depends(get_db)]