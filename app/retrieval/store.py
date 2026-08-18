from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import TIMESTAMP, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import settings

EMBEDDING_DIM = 768

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Document(Base):
    """Mirrors the `documents` table created by migration 73166b138949 -
    this table's DDL is the source of truth; keep this model in sync with it
    by hand rather than autogenerating, since the migration predates the ORM
    layer and stays hand-written raw SQL (see migrations/versions/)."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    """Mirrors the `chunks` table. `content_tsv` is intentionally not mapped
    here - it's a DB-generated column (STORED, computed from `content`), so
    keyword search reads it via raw SQL in search queries below rather than
    through the ORM."""

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


@dataclass(frozen=True, slots=True)
class SearchResult:
    chunk_id: uuid.UUID
    content: str
    chunk_index: int
    doc_type: str
    category: str
    title: str
    source_file: str
    score: float


def _embedding_literal(embedding: Sequence[float]) -> str:
    """pgvector's text input format - passed as a plain string parameter and
    cast with ::vector in SQL, which sidesteps needing driver-level adapter
    registration (pgvector.psycopg.register_vector) for the async engine."""
    return "[" + ",".join(repr(float(v)) for v in embedding) + "]"


async def vector_search(
    session: AsyncSession,
    query_embedding: Sequence[float],
    top_k: int = 10,
    doc_type: str | None = None,
    category: str | None = None,
) -> list[SearchResult]:
    query = text("""
        SELECT c.id, c.content, c.chunk_index, d.doc_type, d.category, d.title, d.source_file,
               1 - (c.embedding <=> (:query_embedding)::vector) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE (CAST(:doc_type AS text) IS NULL OR d.doc_type = CAST(:doc_type AS text))
          AND (CAST(:category AS text) IS NULL OR d.category = CAST(:category AS text))
        ORDER BY c.embedding <=> (:query_embedding)::vector
        LIMIT :top_k
    """)
    result = await session.execute(
        query,
        {
            "query_embedding": _embedding_literal(query_embedding),
            "top_k": top_k,
            "doc_type": doc_type,
            "category": category,
        },
    )
    return [_row_to_result(row) for row in result]


async def keyword_search(
    session: AsyncSession,
    query_text: str,
    top_k: int = 10,
    doc_type: str | None = None,
    category: str | None = None,
) -> list[SearchResult]:
    query = text("""
        SELECT c.id, c.content, c.chunk_index, d.doc_type, d.category, d.title, d.source_file,
               ts_rank(c.content_tsv, plainto_tsquery('english', :query_text)) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.content_tsv @@ plainto_tsquery('english', :query_text)
          AND (CAST(:doc_type AS text) IS NULL OR d.doc_type = CAST(:doc_type AS text))
          AND (CAST(:category AS text) IS NULL OR d.category = CAST(:category AS text))
        ORDER BY score DESC
        LIMIT :top_k
    """)
    result = await session.execute(
        query,
        {
            "query_text": query_text,
            "top_k": top_k,
            "doc_type": doc_type,
            "category": category,
        },
    )
    return [_row_to_result(row) for row in result]


def _row_to_result(row: object) -> SearchResult:
    return SearchResult(
        chunk_id=row.id,  # type: ignore[attr-defined]
        content=row.content,  # type: ignore[attr-defined]
        chunk_index=row.chunk_index,  # type: ignore[attr-defined]
        doc_type=row.doc_type,  # type: ignore[attr-defined]
        category=row.category,  # type: ignore[attr-defined]
        title=row.title,  # type: ignore[attr-defined]
        source_file=row.source_file,  # type: ignore[attr-defined]
        score=row.score,  # type: ignore[attr-defined]
    )


async def replace_document(
    session: AsyncSession,
    *,
    source_file: str,
    doc_type: str,
    category: str,
    title: str,
    chunks: Sequence[tuple[str, int, list[float]]],
) -> None:
    """Delete-then-reinsert a document and its chunks, keyed on source_file.

    Makes re-running scripts/ingest.py idempotent during dev (edit a doc,
    re-ingest, no duplicate/stale chunks left behind) - the corpus is small
    enough that a full replace is simpler and cheap enough to not need a
    real diff/upsert-by-chunk-hash strategy.
    """
    await session.execute(
        text("DELETE FROM documents WHERE source_file = :source_file"),
        {"source_file": source_file},
    )
    document = Document(source_file=source_file, doc_type=doc_type, category=category, title=title)
    session.add(document)
    await session.flush()

    for content, chunk_index, embedding in chunks:
        session.add(
            Chunk(
                document_id=document.id,
                chunk_index=chunk_index,
                content=content,
                embedding=embedding,
            )
        )
    await session.commit()
