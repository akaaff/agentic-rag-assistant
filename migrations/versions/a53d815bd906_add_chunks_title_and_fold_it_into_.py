"""add chunks.title and fold it into content_tsv

Revision ID: a53d815bd906
Revises: 73166b138949
Create Date: 2026-08-18 11:17:16.209273

Fixes a real gap found via live testing: chunking.py drops each doc's H1
title line (the frontmatter title is canonical, so repeating it in every
chunk's embedded content would just be noise), but content_tsv was generated
from `content` alone - so for docs like return-policy.md, whose body never
literally contains the word "policy" (only in the dropped title), keyword
search could never match on that term at all. Confirmed live:
plainto_tsquery('english', "What's your return policy?") requires both
'return' and 'polici' in the same tsvector, and every return-policy.md chunk
failed that match.

Postgres generated columns can only reference columns in their own row, so
folding title into content_tsv requires denormalizing title onto chunks
itself (it already lives on documents, one join away) rather than joining
across tables in the generated expression.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a53d815bd906"
down_revision: str | Sequence[str] | None = "73166b138949"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE chunks ADD COLUMN title TEXT")
    op.execute("""
        UPDATE chunks SET title = documents.title
        FROM documents
        WHERE documents.id = chunks.document_id
    """)
    op.execute("ALTER TABLE chunks ALTER COLUMN title SET NOT NULL")

    op.execute("DROP INDEX chunks_content_tsv_idx")
    op.execute("ALTER TABLE chunks DROP COLUMN content_tsv")
    op.execute("""
        ALTER TABLE chunks ADD COLUMN content_tsv TSVECTOR
        GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || content)) STORED
    """)
    op.execute("CREATE INDEX chunks_content_tsv_idx ON chunks USING gin (content_tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX chunks_content_tsv_idx")
    op.execute("ALTER TABLE chunks DROP COLUMN content_tsv")
    op.execute("""
        ALTER TABLE chunks ADD COLUMN content_tsv TSVECTOR
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
    """)
    op.execute("CREATE INDEX chunks_content_tsv_idx ON chunks USING gin (content_tsv)")
    op.execute("ALTER TABLE chunks DROP COLUMN title")
