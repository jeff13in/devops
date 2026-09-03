"""Shared document loading and chunking utilities for the RAG service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

try:
    import psycopg
    from psycopg import sql
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - checked before ingestion runs
    psycopg = None
    sql = None
    Jsonb = None

from rag.retriever import GoogleGenerativeAIEmbeddings, RetrieverConfig


SUPPORTED_EXTENSIONS = {".md", ".txt"}


@dataclass(slots=True)
class DocumentChunk:
    """A normalized chunk of source content ready for storage or retrieval."""

    source: str
    content: str
    chunk_index: int
    metadata: dict[str, Any] = field(default_factory=dict)


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


@dataclass(slots=True)
class IngestionResult:
    documents_processed: int
    chunks_stored: int


class PgVectorIngestor:
    """Embed local runbook chunks with Gemini and store them in pgvector."""

    def __init__(self, config: RetrieverConfig | None = None) -> None:
        self.config = config or RetrieverConfig()
        self._embedding_client: Any | None = None

    def ingest(self, directory: str | Path) -> IngestionResult:
        chunks = build_chunks(directory)
        if not chunks:
            raise ValueError("No non-empty .md or .txt documents were found.")
        self._ensure_dependencies()

        if self._embedding_client is None:
            self._embedding_client = GoogleGenerativeAIEmbeddings(
                model=self.config.embedding_model
            )
        vectors = list(self._embedding_client.embed_documents([chunk.content for chunk in chunks]))
        if len(vectors) != len(chunks):
            raise RuntimeError("The embedding service returned an unexpected result count.")

        sources = sorted({chunk.source for chunk in chunks})
        delete_statement = sql.SQL("DELETE FROM {table} WHERE source = ANY(%s)").format(
            table=sql.Identifier(self.config.documents_table)
        )
        insert_statement = sql.SQL(
            "INSERT INTO {table} (source, content, metadata, embedding) VALUES (%s, %s, %s, %s::vector)"
        ).format(table=sql.Identifier(self.config.documents_table))
        rows = [
            (
                chunk.source,
                chunk.content,
                Jsonb({**chunk.metadata, "chunk_index": chunk.chunk_index}),
                self._vector_literal(vector),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]

        with psycopg.connect(self.config.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(delete_statement, (sources,))
                cursor.executemany(insert_statement, rows)

        return IngestionResult(len(sources), len(chunks))

    def _ensure_dependencies(self) -> None:
        if psycopg is None or sql is None or Jsonb is None:
            raise RuntimeError("psycopg is required for document ingestion.")
        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY must be configured for ingestion.")
        if GoogleGenerativeAIEmbeddings is None:
            raise RuntimeError("langchain-google-genai is required for document ingestion.")

    @staticmethod
    def _vector_literal(values: list[float]) -> str:
        return "[" + ",".join(f"{value:.10f}" for value in values) + "]"
