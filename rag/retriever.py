"""pgvector-backed similarity retrieval for OpsBrain."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

try:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - handled at runtime by configuration checks
    psycopg = None
    sql = None
    dict_row = None

try:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
except ImportError:  # pragma: no cover - handled at runtime by configuration checks
    GoogleGenerativeAIEmbeddings = None


@dataclass(slots=True)
class RetrievedChunk:
    """A retrieved document chunk returned from vector search."""

    id: str | None
    source: str
    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrieverConfig:
    """Environment-backed configuration for pgvector retrieval."""

    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/opsbrain",
        )
    )
    documents_table: str = field(
        default_factory=lambda: os.getenv("PGVECTOR_TABLE", "document_chunks")
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv(
            "GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001"
        )
    )
    default_top_k: int = field(
        default_factory=lambda: int(os.getenv("RAG_DEFAULT_TOP_K", "4"))
    )
    min_score: float = field(
        default_factory=lambda: float(os.getenv("RAG_MIN_SCORE", "0.2"))
    )
    max_context_chars: int = field(
        default_factory=lambda: int(os.getenv("RAG_MAX_CONTEXT_CHARS", "8000"))
    )


class PgVectorRetriever:
    """Run vector similarity search against a pgvector-backed table."""

    def __init__(
        self,
        config: RetrieverConfig | None = None,
        *,
        embedding_client: Any | None = None,
    ) -> None:
        self.config = config or RetrieverConfig()
        self._embedding_client = embedding_client

    def retrieve(self, query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
        """Embed a query and return the most similar chunks."""

        question = query.strip()
        if len(question) < 5:
            raise ValueError("Question must be at least 5 characters long.")

        self._ensure_dependencies()
        query_vector = self._embed_query(question)
        limit = top_k or self.config.default_top_k
        if limit <= 0:
            raise ValueError("top_k must be greater than zero")

        vector_literal = self._vector_literal(query_vector)
        statement = sql.SQL(
            """
            SELECT
                id,
                source,
                content,
                COALESCE(metadata, '{}'::jsonb) AS metadata,
                1 - (embedding <=> {vector}::vector) AS score
            FROM {table}
            ORDER BY embedding <=> {vector}::vector
            LIMIT %s
            """
        ).format(
            table=sql.Identifier(self.config.documents_table),
            vector=sql.Placeholder(),
        )

        with psycopg.connect(self.config.database_url) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(statement, (vector_literal, vector_literal, limit))
                rows = cursor.fetchall()

        results: list[RetrievedChunk] = []
        for row in rows:
            score = float(row["score"])
            if score < self.config.min_score:
                continue
            results.append(
                RetrievedChunk(
                    id=str(row["id"]) if row.get("id") is not None else None,
                    source=row["source"],
                    content=row["content"],
                    score=score,
                    metadata=dict(row.get("metadata") or {}),
                )
            )
        return results

    def build_context(self, chunks: list[RetrievedChunk]) -> str:
        """Build a bounded prompt context from retrieved chunks."""

        sections: list[str] = []
        total_chars = 0
        for chunk in chunks:
            cleaned_content = chunk.content.strip()
            if not cleaned_content:
                continue
            section = (
                f"Source: {chunk.source}\n"
                f"Relevance: {chunk.score:.3f}\n"
                f"Content:\n{cleaned_content}"
            )
            projected = total_chars + len(section)
            if projected > self.config.max_context_chars and sections:
                break
            if projected > self.config.max_context_chars:
                section = section[: self.config.max_context_chars].rstrip()
            sections.append(section)
            total_chars += len(section)
        return "\n\n---\n\n".join(sections)

    def _ensure_dependencies(self) -> None:
        if psycopg is None or sql is None or dict_row is None:
            raise RuntimeError(
                "psycopg is required for vector retrieval. Install requirements first."
            )
        if self._embedding_client is None and GoogleGenerativeAIEmbeddings is None:
            raise RuntimeError(
                "langchain-google-genai is required for embeddings. Install requirements first."
            )

    def _embed_query(self, query: str) -> list[float]:
        client = self._embedding_client
        if client is None:
            client = GoogleGenerativeAIEmbeddings(model=self.config.embedding_model)
            self._embedding_client = client
        return list(client.embed_query(query))

    @staticmethod
    def _vector_literal(values: list[float]) -> str:
        return "[" + ",".join(f"{value:.10f}" for value in values) + "]"
