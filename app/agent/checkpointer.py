from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import settings


def _psycopg_conn_string() -> str:
    # AsyncPostgresSaver connects via raw psycopg, not SQLAlchemy, so it
    # needs the plain `postgresql://` scheme - SQLAlchemy's dialect-prefixed
    # `postgresql+psycopg://` (what DATABASE_URL actually is, for the
    # SQLAlchemy engine in retrieval/store.py) isn't a valid psycopg DSN.
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://")


@asynccontextmanager
async def get_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    """Session-state checkpointer, keyed by thread_id (the chat session id).

    Verified live: `checkpointer.setup()` creates its own tables
    (checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations)
    via its own internal migration system - deliberately NOT tracked by our
    Alembic migrations in migrations/, since that's LangGraph's own state,
    not application schema we own. Same Postgres instance as pgvector
    (infra/docker-compose.yml), separate table set.
    """
    async with AsyncPostgresSaver.from_conn_string(_psycopg_conn_string()) as checkpointer:
        await checkpointer.setup()
        yield checkpointer
