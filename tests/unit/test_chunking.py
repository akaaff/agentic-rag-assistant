from pathlib import Path

import pytest

from app.retrieval.chunking import chunk_corpus, chunk_document, parse_frontmatter

FIXTURE_DOC = """\
---
doc_type: policy
category: widgets
title: Widget Policy
---

# Widget Policy

## Section one

Body text for section one.

## Section two

Body text for section two.
"""


def test_parse_frontmatter_extracts_metadata_and_body() -> None:
    metadata, body = parse_frontmatter(FIXTURE_DOC)

    assert metadata == {"doc_type": "policy", "category": "widgets", "title": "Widget Policy"}
    assert "# Widget Policy" in body
    assert "Section one" in body


def test_parse_frontmatter_requires_frontmatter() -> None:
    with pytest.raises(ValueError, match="frontmatter"):
        parse_frontmatter("# No frontmatter here\n\nJust body text.\n")


def test_chunk_document_splits_on_h2_and_drops_h1(tmp_path: Path) -> None:
    doc_path = tmp_path / "widget-policy.md"
    doc_path.write_text(FIXTURE_DOC, encoding="utf-8")

    chunks = chunk_document(doc_path)

    assert len(chunks) == 2
    assert [c.section_title for c in chunks] == ["Section one", "Section two"]
    assert [c.chunk_index for c in chunks] == [0, 1]
    for chunk in chunks:
        assert chunk.doc_type == "policy"
        assert chunk.category == "widgets"
        assert chunk.title == "Widget Policy"
        assert chunk.source_file == "widget-policy.md"
        # The H1 title line is dropped - only the frontmatter carries it.
        assert "# Widget Policy" not in chunk.content


def test_chunk_document_splits_long_sections(tmp_path: Path) -> None:
    long_body = "\n\n".join(f"Paragraph {i} of the long section." * 5 for i in range(10))
    doc = f"""---
doc_type: policy
category: widgets
title: Long Doc
---

# Long Doc

## Only section

{long_body}
"""
    doc_path = tmp_path / "long-doc.md"
    doc_path.write_text(doc, encoding="utf-8")

    chunks = chunk_document(doc_path, max_chars=200)

    assert len(chunks) > 1
    assert all(c.section_title == "Only section" for c in chunks)
    # chunk_index should be contiguous even across a split section.
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunk_corpus_reads_every_markdown_file(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(FIXTURE_DOC, encoding="utf-8")
    (tmp_path / "b.md").write_text(
        FIXTURE_DOC.replace("Widget Policy", "Gadget Policy"), encoding="utf-8"
    )
    (tmp_path / "not-markdown.txt").write_text("ignore me", encoding="utf-8")

    chunks = chunk_corpus(tmp_path)

    assert {c.source_file for c in chunks} == {"a.md", "b.md"}
    assert len(chunks) == 4
