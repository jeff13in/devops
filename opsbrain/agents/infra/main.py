"""FastAPI entry point for the OpsBrain Infra Agent — Stage 2.

Will query AWS (boto3), Kubernetes, and Terraform plan outputs.
Currently returns stubs so docker-compose can start cleanly.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="OpsBrain — Infra Agent", version="0.1.0")


class QueryRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok", "agent": "infra"}


@app.post("/query")
def query(request: QueryRequest):
    from agents.infra.agent import run_infra_agent
    return run_infra_agent(request.question)
