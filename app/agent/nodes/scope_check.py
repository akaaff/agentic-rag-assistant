from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from app.agent.context import last_user_text
from app.agent.state import GraphState
from app.guardrails.scope import ACTION_DECLINE_TEMPLATE, is_action_request


async def scope_check_node(state: GraphState) -> dict[str, Any]:
    """Graph's entry point, before router. If the question is an action
    request (see guardrails/scope.py), writes the decline itself - a fixed
    template, no LLM call - and the graph routes straight to END from here,
    never reaching router/retrieve/tools/critique/answer. Otherwise a no-op:
    just signals the normal flow should continue."""
    text = last_user_text(state)
    if is_action_request(text):
        return {
            "is_out_of_scope_action": True,
            "messages": [AIMessage(content=ACTION_DECLINE_TEMPLATE)],
        }
    return {"is_out_of_scope_action": False}
