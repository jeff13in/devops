"""Orchestrator LangGraph state machine — Stage 2.

The full graph will:
  1. route       — decide which agents to call (parallel fan-out)
  2. gather      — collect all agent responses
  3. synthesise  — merge answers into a single coherent reply
  4. END

Stage 1: the state definition and node skeletons are here so Stage 2
can fill in the bodies without restructuring the file.
"""

from typing import Dict, List, TypedDict

from langgraph.graph import END, StateGraph


class OrchestratorState(TypedDict):
    question: str
    agents_to_call: List[str]
    agent_responses: Dict[str, dict]
    final_answer: str


def route_node(state: OrchestratorState) -> OrchestratorState:
    """Decide which agents should handle the question."""
    from orchestrator.router import route
    return {**state, "agents_to_call": route(state["question"])}


def gather_node(state: OrchestratorState) -> OrchestratorState:
    """Call each chosen agent (HTTP) and collect responses."""
    # TODO Stage 2: fan-out with asyncio.gather over agent HTTP endpoints
    return {**state, "agent_responses": {}}


def synthesise_node(state: OrchestratorState) -> OrchestratorState:
    """Merge all agent responses into one coherent answer."""
    # TODO Stage 2: second LLM call to synthesise multi-agent results
    return {**state, "final_answer": "Orchestrator synthesis not yet implemented."}


def build_orchestrator_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("route",      route_node)
    graph.add_node("gather",     gather_node)
    graph.add_node("synthesise", synthesise_node)
    graph.set_entry_point("route")
    graph.add_edge("route",      "gather")
    graph.add_edge("gather",     "synthesise")
    graph.add_edge("synthesise", END)
    return graph.compile()
