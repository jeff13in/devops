"""Orchestrator router — Stage 2.

Inspects the user's question and decides which subset of agents to call.
The routing logic will use an LLM classifier in Stage 2. For now,
the function signature and return type are defined so Stage 2 can plug in.
"""

from typing import List


# Mapping of agent names to their internal service URLs (set via env in prod)
AGENT_URLS = {
    "rag":        "http://rag-agent:8001",
    "monitoring": "http://monitoring-agent:8002",
    "infra":      "http://infra-agent:8003",
    "code":       "http://code-agent:8004",
}


def route(question: str) -> List[str]:
    """Return the list of agent names that should handle this question.

    Stage 2 implementation: call gpt-4o with a routing prompt and parse the
    JSON list of agent names it returns. For now, always route to RAG.
    """
    # TODO Stage 2: replace with LLM-based classifier
    return ["rag"]
