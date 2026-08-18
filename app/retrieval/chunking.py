from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

MAX_CHUNK_CHARS = 1000

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Chunk:
    content: str
    doc_type: str
    category: str
    title: str
    section_title: str
    source_file: str
    chunk_index: int


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a doc into its YAML frontmatter dict and the markdown body after it."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("Document is missing required YAML frontmatter (doc_type/category/title)")
    metadata = yaml.safe_load(match.group(1))
    body = text[match.end() :]
    return metadata, body


def _split_into_sections(body: str) -> list[tuple[str, str]]:
    """Split the body into (heading, section_text) pairs on H2 boundaries.

    Content before the first H2 (i.e. the doc's H1 title line) is dropped -
    the frontmatter's `title` field is the canonical title, so repeating it
    as body text in every doc would just add noise to what gets embedded.
    """
    headings = list(_H2_RE.finditer(body))
    if not headings:
        return [("", body.strip())]

    sections = []
    for i, match in enumerate(headings):
        heading = match.group(1).strip()
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
        sections.append((heading, body[start:end].strip()))
    return sections


def _split_long_section(text: str, max_chars: int) -> list[str]:
    """Paragraph-split a section only if it exceeds max_chars.

    None of the current docs need this (every H2 section is well under the
    limit) - it exists so a future, longer doc doesn't silently become one
    oversized chunk that hurts retrieval precision.
    """
    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    parts: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) > max_chars and current:
            parts.append(current)
            current = para
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts or [text]


def chunk_document(path: Path, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    text = path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)

    chunks: list[Chunk] = []
    index = 0
    for heading, section_text in _split_into_sections(body):
        for part in _split_long_section(section_text, max_chars):
            content = f"{heading}\n\n{part}" if heading else part
            chunks.append(
                Chunk(
                    content=content.strip(),
                    doc_type=metadata["doc_type"],
                    category=metadata["category"],
                    title=metadata["title"],
                    section_title=heading,
                    source_file=path.name,
                    chunk_index=index,
                )
            )
            index += 1
    return chunks


def chunk_corpus(corpus_dir: Path, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    for path in sorted(corpus_dir.glob("*.md")):
        all_chunks.extend(chunk_document(path, max_chars=max_chars))
    return all_chunks
