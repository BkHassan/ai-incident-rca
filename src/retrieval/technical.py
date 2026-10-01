"""Chunk technical markdown and search those chunks."""

from __future__ import annotations

from pathlib import Path

from .models import RetrievalError, TechnicalDocumentResult
from .scoring import ranked_query

SOURCE_TYPE = "technical_document"
DOC_NAMES = ("database.md", "memory.md", "networking.md", "troubleshooting.md")
_MIN_SECTION_CHARS = 280
_MAX_SECTION_CHARS = 1800


def technical_dir(root: Path) -> Path:
    return root / "knowledge" / "docs"


def load_technical_chunks(directory: Path) -> list[dict]:
    chunks: list[dict] = []
    for name in DOC_NAMES:
        path = directory / name
        if not path.is_file():
            raise RetrievalError(f"missing technical document {path}")
        chunks.extend(chunk_markdown(path))
    return chunks


def chunk_markdown(path: Path) -> list[dict]:
    """Split one markdown file on ``##`` headings. Each chunk stands on its own."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    title = path.stem
    for line in text.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break
    sections = _sections(text)
    if not sections:
        raise RetrievalError(f"{path.name} has no ## sections")
    pieces: list[tuple[str, str]] = []
    for heading, body in sections:
        parts = _split_long(body, _MAX_SECTION_CHARS)
        for index, part in enumerate(parts, start=1):
            section = heading if len(parts) == 1 else f"{heading} (part {index})"
            pieces.append((section, part))
    merged = _merge_short(pieces, _MIN_SECTION_CHARS)
    chunks = []
    for number, (section, body) in enumerate(merged, start=1):
        chunk_id = f"{path.stem}_{number:03d}"
        rendered = f"Document: {title}\nSection: {section}\n\n{body.strip()}\n"
        chunks.append({
            "id": chunk_id,
            "text": rendered,
            "metadata": {
                "document_id": chunk_id,
                "document_name": path.name,
                "section": section,
                "source_type": SOURCE_TYPE,
            },
        })
    return chunks


def retrieve_technical_documents(
    collection, embedder, query_text: str, top_k: int = 3
) -> list[TechnicalDocumentResult]:
    hits = ranked_query(collection, embedder, query_text, top_k)
    results = []
    for rank, hit in enumerate(hits, start=1):
        metadata = hit["metadata"]
        results.append(TechnicalDocumentResult(
            rank=rank,
            document_id=str(metadata.get("document_id") or hit["id"]),
            section=str(metadata.get("section", "")),
            score=hit["score"],
            text=hit["text"],
            metadata=metadata,
        ))
    return results


def _sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading: str | None = None
    buf: list[str] = []
    for line in text.split("\n"):
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(buf).strip()))
            heading = line[3:].strip()
            buf = []
        elif heading is not None:
            buf.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(buf).strip()))
    return sections


def _split_long(body: str, limit: int) -> list[str]:
    if len(body) <= limit:
        return [body]
    paragraphs = [part.strip() for part in body.split("\n\n") if part.strip()]
    groups: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if current and len(candidate) > limit:
            groups.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        groups.append(current)
    return groups or [body]


def _merge_short(pieces: list[tuple[str, str]], minimum: int) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    index = 0
    while index < len(pieces):
        section, body = pieces[index]
        while index + 1 < len(pieces) and len(body) < minimum:
            index += 1
            next_section, next_body = pieces[index]
            section = f"{section} / {next_section}"
            body = body + "\n\n" + next_body
        merged.append((section, body))
        index += 1
    if len(merged) >= 2 and len(merged[-1][1]) < minimum:
        previous_section, previous_body = merged[-2]
        last_section, last_body = merged[-1]
        merged[-2] = (f"{previous_section} / {last_section}", previous_body + "\n\n" + last_body)
        merged.pop()
    return merged
