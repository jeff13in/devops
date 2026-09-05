"""Shared configuration for all OpsBrain agents.

Loads every setting from environment variables (or a .env file).
Import `settings` from this module — never access os.environ directly.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Google Gemini (AI Studio) ─────────────────────────────────────────
    google_api_key: str
    google_embedding_model: str = "models/gemini-embedding-001"
    google_chat_model: str = "gemini-3.6-flash"

    # ── PostgreSQL / pgvector ────────────────────────────────────────────
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "opsbrain"
    postgres_user: str = "opsbrain"
    postgres_password: str

    # ── Kafka ────────────────────────────────────────────────────────────
    kafka_bootstrap_servers: str = "kafka:9092"

    # ── RAG tuning ───────────────────────────────────────────────────────
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_top_k: int = 5

    model_config = {"env_file": ".env"}


settings = Settings()
