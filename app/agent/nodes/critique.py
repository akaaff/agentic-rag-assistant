from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agent.context import format_context
from app.agent.llm import get_chat_model
from app.agent.prompts.critique import CRITIQUE_SYSTEM_PROMPT
from app.agent.state import GraphState


class CritiqueVerdict(BaseModel):
    grounded: bool = Field(
        description="Whether the gathered context supports an accurate, specific answer"
    )


async def critique_node(state: GraphState) -> dict[str, str]:
    llm = get_chat_model().with_structured_output(CritiqueVerdict)
    context = format_context(state)
    verdict = await llm.ainvoke(
        [
            SystemMessage(CRITIQUE_SYSTEM_PROMPT),
            *state["messages"],
            HumanMessage(f"Gathered context:\n{context}"),
        ]
    )
    assert isinstance(verdict, CritiqueVerdict)
    return {"critique_verdict": "grounded" if verdict.grounded else "ungrounded"}
