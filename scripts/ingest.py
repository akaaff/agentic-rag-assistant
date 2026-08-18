"""Ingest docs_corpus/*.md into pgvector: chunk -> embed -> store.

Idempotent per source_file (replace_document deletes+reinserts), so safe to
re-run after editing a doc.

Usage: uv run python scripts/ingest.py
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path

from app import asyncio_compat
from app.retrieval.chunking import Chunk, chunk_corpus
from app.retrieval.embeddings import OllamaEmbeddingsClient
from app.retrieval.store import async_session_factory, replace_document

CORPUS_DIR = Path(__file__).resolve().parent.parent / "docs_corpus"


async def ingest() -> None:
    chunks = chunk_corpus(CORPUS_DIR)
    if not chunks:
        print(f"No documents found in {CORPUS_DIR}")
        return

    embeddings_client = OllamaEmbeddingsClient()
    embeddings = await embeddings_client.embed([c.content for c in chunks])

    grouped: dict[str, list[tuple[Chunk, list[float]]]] = defaultdict(list)
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        grouped[chunk.source_file].append((chunk, embedding))

    async with async_session_factory() as session:
        for source_file, pairs in grouped.items():
            first_chunk = pairs[0][0]
            await replace_document(
                session,
                source_file=source_file,
                doc_type=first_chunk.doc_type,
                category=first_chunk.category,
                title=first_chunk.title,
                chunks=[
                    (chunk.content, chunk.chunk_index, embedding) for chunk, embedding in pairs
                ],
            )
            print(f"Ingested {source_file}: {len(pairs)} chunks")


if __name__ == "__main__":
    asyncio_compat.apply()
    asyncio.run(ingest())
