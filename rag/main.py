"""FastAPI entrypoint for the OpsBrain RAG agent."""

from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from rag.agent import AgentResponse, RAGAgent


app = FastAPI(
    title="OpsBrain RAG Agent",
    version="0.1.0",
    description="Retrieve runbook context from pgvector and answer DevOps questions.",
)


class QueryRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    top_k: int = Field(default=4, ge=1, le=10)


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    grounded: bool
    validation_errors: list[str]
    retrieved_chunks: int


class HealthResponse(BaseModel):
    status: str


@lru_cache(maxsize=1)
def get_agent() -> RAGAgent:
    return RAGAgent()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/query", response_model=QueryResponse)
def query_rag(request: QueryRequest) -> QueryResponse:
    try:
        response: AgentResponse = get_agent().ask(
            request.question,
            top_k=request.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safety net for service failures
        raise HTTPException(status_code=500, detail="Failed to query the RAG agent.") from exc

    return QueryResponse(
        answer=response.answer,
        sources=response.sources,
        grounded=response.grounded,
        validation_errors=response.validation_errors,
        retrieved_chunks=response.retrieved_chunks,
    )
