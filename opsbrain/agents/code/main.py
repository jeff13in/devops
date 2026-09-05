"""FastAPI entry point for the OpsBrain Code Agent — Stage 2.

Will read GitHub PRs, trigger GitHub Actions, and check CI/CD status.
Currently returns stubs so docker-compose can start cleanly.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="OpsBrain — Code Agent", version="0.1.0")


class QueryRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok", "agent": "code"}


@app.post("/query")
def query(request: QueryRequest):
    from agents.code.agent import run_code_agent
    return run_code_agent(request.question)
