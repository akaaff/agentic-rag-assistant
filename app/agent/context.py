from __future__ import annotations

from langchain_core.messages import HumanMessage, ToolMessage

from app.agent.state import GraphState
from app.guardrails.injection import wrap_untrusted_content


def last_user_text(state: GraphState) -> str:
    """Most recent HumanMessage's text - shared by retrieve_node (query for
    hybrid search) and scope_check_node (text to run the action-request
    check against)."""
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
    raise ValueError("No user message found in state")


def format_context(state: GraphState) -> str:
    """Render retrieved docs + tool results (already in message history) as
    a plain-text block for the critique/answer nodes' final LLM call.
    Shared by both nodes so they judge/answer from the exact same context.

    Each piece is wrapped via wrap_untrusted_content (see
    guardrails/injection.py) - retrieved doc text and tool results are
    external content, not instructions, and should never be treated as
    such even if a chunk contains something that reads like a command.
    """
    parts: list[str] = []
    if state["retrieved_docs"]:
        parts.append("Retrieved doc excerpts:")
        for doc in state["retrieved_docs"]:
            parts.append(wrap_untrusted_content(doc.source_file, doc.content))

    tool_results = [m.content for m in state["messages"] if isinstance(m, ToolMessage)]
    if tool_results:
        parts.append("Tool results:")
        for i, result in enumerate(tool_results):
            parts.append(wrap_untrusted_content(f"tool_result_{i}", str(result)))

    if not parts:
        parts.append("(no retrieved docs or tool results)")
    return "\n".join(parts)
