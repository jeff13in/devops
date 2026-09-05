"""Shared Pydantic models used across all OpsBrain agents.

Define every cross-agent data shape here so each microservice speaks
the same language without duplicating model code.
"""

from typing import Any, Dict, List
from pydantic import BaseModel


# ── RAG Agent ────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    top_k: int = 5


class DocumentChunk(BaseModel):
    content: str
    source: str
    chunk_id: int
    metadata: Dict[str, Any] = {}


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: List[str]
    agent: str = "rag"


class IngestRequest(BaseModel):
    directory: str = "./docs"


class IngestResponse(BaseModel):
    status: str
    files_processed: int
    chunks_stored: int


# ── Inter-Agent Messaging (Kafka) ─────────────────────────────────────────────

class AgentMessage(BaseModel):
    """Message envelope passed between agents over Kafka."""
    task_id: str
    from_agent: str
    to_agent: str
    payload: Dict[str, Any]
