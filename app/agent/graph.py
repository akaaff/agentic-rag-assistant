from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes.answer import answer_node
from app.agent.nodes.critique import critique_node
from app.agent.nodes.retrieve import retrieve_node
from app.agent.nodes.router import router_node
from app.agent.nodes.tools import tools_node
from app.agent.state import MAX_TOOL_CALLS, GraphState


def _after_router(state: GraphState) -> str:
    if state["needs_retrieval"]:
        return "retrieve"
    if state["needs_tools"]:
        return "tools"
    return "critique"


def _after_retrieve(state: GraphState) -> str:
    return "tools" if state["needs_tools"] else "critique"


def _after_tools(state: GraphState) -> str:
    if state["needs_more_tools"] and state["tool_call_count"] < MAX_TOOL_CALLS:
        return "tools"
    return "critique"


def _after_critique(state: GraphState) -> str:
    if state["critique_verdict"] == "grounded" or state["retried"]:
        return "answer"
    return "mark_retry"


async def _mark_retry(state: GraphState) -> dict[str, bool]:
    """A retry needs to flip `retried` in state before looping back to
    router - a conditional edge function can only choose where to go, it
    can't itself write to state, so this tiny node does the write."""
    return {"retried": True}


def build_graph() -> StateGraph:  # type: ignore[type-arg]
    # StateGraph's generic params (StateT/ContextT/InputT/OutputT) are
    # TypeVars defined across several internal langgraph modules with no
    # locally-visible defaults - rather than guess at the right 4-tuple,
    # this is the one deliberate type: ignore boundary for LangGraph's
    # generics in this module.
    graph = StateGraph(GraphState)

    graph.add_node("router", router_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("tools", tools_node)
    graph.add_node("critique", critique_node)
    graph.add_node("mark_retry", _mark_retry)
    graph.add_node("answer", answer_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", _after_router, ["retrieve", "tools", "critique"])
    graph.add_conditional_edges("retrieve", _after_retrieve, ["tools", "critique"])
    graph.add_conditional_edges("tools", _after_tools, ["tools", "critique"])
    graph.add_conditional_edges("critique", _after_critique, ["answer", "mark_retry"])
    graph.add_edge("mark_retry", "router")
    graph.add_edge("answer", END)

    return graph


def compile_graph(
    checkpointer: BaseCheckpointSaver | None = None,  # type: ignore[type-arg]
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Compiled, ready-to-invoke graph. Caller (Day 7's FastAPI app, or a
    test) is responsible for supplying the full initial state on first
    invocation - GraphState is a TypedDict with no defaults:
    {messages, customer_jwt, needs_retrieval: False, needs_tools: False,
    retrieved_docs: [], tool_call_count: 0, needs_more_tools: False,
    critique_verdict: None, retried: False}."""
    return build_graph().compile(checkpointer=checkpointer)
