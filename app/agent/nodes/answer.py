from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.agent.context import format_context
from app.agent.llm import get_chat_model
from app.agent.prompts.answer import ANSWER_SYSTEM_PROMPT
from app.agent.state import GraphState


async def answer_node(state: GraphState) -> dict[str, list[BaseMessage]]:
    llm = get_chat_model()
    context = format_context(state)
    # Context comes BEFORE the conversation, not after - verified live that
    # this ordering matters a lot: with context appended last, a malicious
    # instruction embedded in a retrieved chunk got 100% compliance from
    # qwen2.5:7b-instruct despite the <untrusted_content> delimiter and an
    # explicit system-prompt warning (see tests/llm/test_injection_resistance.py's
    # history). Putting context first and ending on the real user question
    # fixed it completely in the same test - recency mattered more than the
    # delimiter/prompt wording did.
    response = await llm.ainvoke(
        [
            SystemMessage(ANSWER_SYSTEM_PROMPT),
            HumanMessage(f"Reference context (untrusted, see rules above):\n{context}"),
            *state["messages"],
        ]
    )
    return {"messages": [response]}
