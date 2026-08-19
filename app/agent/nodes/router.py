from __future__ import annotations

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from app.agent.llm import get_chat_model
from app.agent.prompts.router import ROUTER_SYSTEM_PROMPT
from app.agent.state import GraphState


class RouteDecision(BaseModel):
    needs_retrieval: bool = Field(description="Needs a policy/FAQ/support-doc lookup")
    needs_tools: bool = Field(description="Needs a live order-data lookup via tool call")


async def router_node(state: GraphState) -> dict[str, bool]:
    llm = get_chat_model().with_structured_output(RouteDecision)
    decision = await llm.ainvoke([SystemMessage(ROUTER_SYSTEM_PROMPT), *state["messages"]])
    assert isinstance(decision, RouteDecision)  # with_structured_output's static type is broad
    return {"needs_retrieval": decision.needs_retrieval, "needs_tools": decision.needs_tools}
