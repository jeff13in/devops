"""FastAPI entrypoint for the OpsBrain Code Agent."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from agents.code.agent import CodeAgent, CodeClientError

app = FastAPI(
    title="OpsBrain Code Agent",
    version="0.1.0",
    description="Query GitHub pull requests and GitHub Actions CI/CD pipeline status.",
)


class HealthResponse(BaseModel):
    status: str
    repo: str | None
    github_token_configured: bool


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class PullRequestListResponse(BaseModel):
    repo: str
    state: str
    count: int
    pull_requests: list[dict[str, Any]]


class WorkflowRunListResponse(BaseModel):
    repo: str
    count: int
    workflow_runs: list[dict[str, Any]]


@lru_cache(maxsize=1)
def get_agent() -> CodeAgent:
    return CodeAgent()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(**get_agent().health())


@app.post("/query")
def query(request: QueryRequest) -> dict[str, Any]:
    return get_agent().ask(request.question)


@app.get("/pulls", response_model=PullRequestListResponse)
def list_pulls(
    state: str = Query(default="open", pattern="^(open|closed|all)$"),
    limit: int = Query(default=10, ge=1, le=100),
) -> PullRequestListResponse:
    try:
        return PullRequestListResponse(**get_agent().list_pull_requests(state=state, limit=limit))
    except CodeClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/pulls/{number}")
def get_pull(number: int) -> dict[str, Any]:
    try:
        return get_agent().get_pull_request(number)
    except CodeClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/pulls/{number}/status")
def get_pull_status(number: int) -> dict[str, Any]:
    try:
        return get_agent().get_pull_request_status(number)
    except CodeClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/actions/runs", response_model=WorkflowRunListResponse)
def list_runs(
    branch: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
) -> WorkflowRunListResponse:
    try:
        return WorkflowRunListResponse(
            **get_agent().list_workflow_runs(branch=branch, status=status, limit=limit)
        )
    except CodeClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/actions/summary")
def actions_summary(branch: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        return get_agent().summarize_ci(branch=branch)
    except CodeClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
