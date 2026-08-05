from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..models import PullRequestData, HeuristicResult, RAGContext
from .nodes import (
    api_agent,
    coordinator_node,
    database_agent,
    judge_node,
    performance_agent,
    security_agent,
    tests_agent,
)
from .state import AgentState

_AGENT_NODES = {
    "security": security_agent,
    "performance": performance_agent,
    "database": database_agent,
    "api": api_agent,
    "tests": tests_agent,
}

_compiled_graph = None


def _build_graph():
    builder = StateGraph(AgentState)

    for name, node_fn in _AGENT_NODES.items():
        builder.add_node(name, node_fn)
        builder.add_edge(START, name)
        builder.add_edge(name, "coordinator")

    builder.add_node("coordinator", coordinator_node)
    builder.add_node("judge", judge_node)
    builder.add_edge("coordinator", "judge")
    builder.add_edge("judge", END)

    return builder.compile()


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()
    return _compiled_graph


async def run_pipeline(pr: PullRequestData, heuristics: HeuristicResult, rag: RAGContext) -> AgentState:
    graph = get_graph()
    initial_state: AgentState = {"pr": pr, "heuristics": heuristics, "rag": rag}
    final_state = await graph.ainvoke(initial_state)
    return final_state
