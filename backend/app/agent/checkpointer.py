"""LangGraph conversation memory stored in PostgreSQL (Neon)."""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import get_settings

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None


async def init_checkpointer() -> AsyncPostgresSaver:
    global _pool, _checkpointer
    _pool = AsyncConnectionPool(
        conninfo=get_settings().database_url,  # plain URL: psycopg understands sslmode
        max_size=5,
        # autocommit + no prepared statements: required for Neon's pooled endpoint
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()  # creates LangGraph's tables if missing
    return _checkpointer


async def close_checkpointer() -> None:
    if _pool is not None:
        await _pool.close()


def get_checkpointer() -> AsyncPostgresSaver:
    if _checkpointer is None:
        raise RuntimeError("Checkpointer not initialised")
    return _checkpointer