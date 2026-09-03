"""Shared document loading and chunking utilities for the RAG service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


SUPPORTED_EXTENSIONS = {".md", ".txt"}


@dataclass(slots=True)
class DocumentChunk:
    """A normalized chunk of source content ready for storage or retrieval."""

    source: str
    content: str
    chunk_index: int
    metadata: dict[str, str] = field(default_factory=dict)


def load_documents(directory: str | Path) -> list[tuple[Path, str]]:
    """Load supported text documents from a directory tree."""

    root = Path(directory).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root}")

    documents: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if text.strip():
            documents.append((path, text))
    return documents


def chunk_text(
    text: str,
    *,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> list[str]:
    """Split text into overlapping chunks without breaking on tiny fragments."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap cannot be negative")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    normalized = " ".join(text.split())
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    step = chunk_size - chunk_overlap
    while start < len(normalized):
        end = start + chunk_size
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start += step
    return chunks


def build_chunks(
    directory: str | Path,
    *,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> list[DocumentChunk]:
    """Load all supported files in a directory and return chunk records."""

    chunk_records: list[DocumentChunk] = []
    for path, text in load_documents(directory):
        relative_source = path.name
        for index, chunk in enumerate(
            chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        ):
            chunk_records.append(
                DocumentChunk(
                    source=relative_source,
                    content=chunk,
                    chunk_index=index,
                    metadata={
                        "path": str(path),
                        "filename": path.name,
                    },
                )
            )
    return chunk_records


def iter_chunk_payloads(chunks: list[DocumentChunk]) -> Iterator[dict[str, object]]:
    """Yield simple dictionaries for bulk inserts or API serialization."""

    for chunk in chunks:
        yield {
            "source": chunk.source,
            "content": chunk.content,
            "chunk_index": chunk.chunk_index,
            "metadata": chunk.metadata,
        }
