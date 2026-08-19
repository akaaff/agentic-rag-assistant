from __future__ import annotations

from langchain_core.messages import ToolMessage

from app.agent.state import GraphState


def format_context(state: GraphState) -> str:
    """Render retrieved docs + tool results (already in message history) as
    a plain-text block for the critique/answer nodes' final LLM call.
    Shared by both nodes so they judge/answer from the exact same context."""
    parts: list[str] = []
    if state["retrieved_docs"]:
        parts.append("Retrieved doc excerpts:")
        for doc in state["retrieved_docs"]:
            parts.append(f"- [{doc.source_file}] {doc.content}")

    tool_results = [m.content for m in state["messages"] if isinstance(m, ToolMessage)]
    if tool_results:
        parts.append("Tool results:")
        parts.extend(f"- {r}" for r in tool_results)

    if not parts:
        parts.append("(no retrieved docs or tool results)")
    return "\n".join(parts)
