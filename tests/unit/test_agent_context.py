import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.context import format_context, last_user_text
from app.retrieval.store import SearchResult


def test_last_user_text_finds_the_most_recent_human_message() -> None:
    messages = [
        HumanMessage("first question"),
        AIMessage("first answer"),
        HumanMessage("second question"),
    ]

    assert last_user_text({"messages": messages}) == "second question"  # type: ignore[typeddict-item]


def test_last_user_text_ignores_system_and_ai_messages() -> None:
    messages = [
        SystemMessage("system prompt"),
        HumanMessage("the actual question"),
        AIMessage("an answer"),
    ]

    assert last_user_text({"messages": messages}) == "the actual question"  # type: ignore[typeddict-item]


def test_last_user_text_raises_when_no_human_message() -> None:
    messages = [SystemMessage("system prompt"), AIMessage("an answer")]

    with pytest.raises(ValueError, match="No user message"):
        last_user_text({"messages": messages})  # type: ignore[typeddict-item]


def test_format_context_wraps_retrieved_docs_as_untrusted_content() -> None:
    doc = SearchResult(
        chunk_id=uuid.uuid4(),
        content="Some policy text.",
        chunk_index=0,
        doc_type="policy",
        category="general",
        title="Doc",
        source_file="policy.md",
        score=0.9,
    )
    state = {"retrieved_docs": [doc], "messages": []}

    context = format_context(state)  # type: ignore[arg-type]

    assert '<untrusted_content source="policy.md">' in context
    assert "Some policy text." in context
    assert "</untrusted_content>" in context


def test_format_context_wraps_tool_results_as_untrusted_content() -> None:
    state = {
        "retrieved_docs": [],
        "messages": [ToolMessage(content="Order X is CANCELLED", tool_call_id="1")],
    }

    context = format_context(state)  # type: ignore[arg-type]

    assert '<untrusted_content source="tool_result_0">' in context
    assert "Order X is CANCELLED" in context


def test_format_context_handles_empty_state() -> None:
    state: dict[str, list[object]] = {"retrieved_docs": [], "messages": []}

    assert format_context(state) == "(no retrieved docs or tool results)"  # type: ignore[arg-type]
