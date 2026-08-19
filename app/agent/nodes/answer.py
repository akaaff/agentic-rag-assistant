from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.agent.context import format_context
from app.agent.llm import get_chat_model
from app.agent.prompts.answer import ANSWER_SYSTEM_PROMPT
from app.agent.state import GraphState


async def answer_node(state: GraphState) -> dict[str, list[BaseMessage]]:
    llm = get_chat_model()
    context = format_context(state)
    response = await llm.ainvoke(
        [
            SystemMessage(ANSWER_SYSTEM_PROMPT),
            *state["messages"],
            HumanMessage(f"Gathered context:\n{context}"),
        ]
    )
    return {"messages": [response]}
