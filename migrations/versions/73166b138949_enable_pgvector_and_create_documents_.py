"""enable pgvector and create documents/chunks tables

Revision ID: 73166b138949
Revises:
Create Date: 2026-08-17 15:16:24.566631

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "73166b138949"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 768 = nomic-embed-text's output dimension. If the embedding model ever
# changes, this column (and the HNSW index below) need a new migration -
# pgvector's VECTOR(n) is a fixed dimension, not a max length.
EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_file TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute(f"""
        CREATE TABLE chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding VECTOR({EMBEDDING_DIM}) NOT NULL,
            content_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (document_id, chunk_index)
        )
    """)

    # HNSW over ivfflat: ivfflat needs a representative data sample to build
    # good list centroids, which doesn't exist yet for a corpus this size
    # anyway - HNSW builds incrementally and has no such cold-start problem.
    op.execute(
        "CREATE INDEX chunks_embedding_hnsw_idx ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX chunks_content_tsv_idx ON chunks USING gin (content_tsv)")
    op.execute("CREATE INDEX chunks_document_id_idx ON chunks (document_id)")
    op.execute("CREATE INDEX documents_doc_type_idx ON documents (doc_type)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS documents")
