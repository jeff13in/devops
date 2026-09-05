"""FastAPI entry point for the OpsBrain Orchestrator — Stage 2.

The Orchestrator is the single public-facing API. Users (CLI or Slack)
send questions here; it routes them to the right agents, collects answers,
and returns a unified response.

Stage 1: The /query endpoint routes every question directly to the RAG agent.
Stage 2: Replace with full LangGraph fan-out once all agents are live.
"""

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="OpsBrain Orchestrator", version="0.1.0")

RAG_AGENT_URL = "http://rag-agent:8001"


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok", "agent": "orchestrator"}


@app.post("/ask")
def ask(request: AskRequest):
    """Route the question through the agent graph and return a unified answer."""
    # Stage 1: forward directly to RAG agent
    try:
        resp = httpx.post(
            f"{RAG_AGENT_URL}/query",
            json={"question": request.question},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"RAG agent error: {exc}")
