import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.nodes.retrieve import _last_user_text


def test_last_user_text_finds_the_most_recent_human_message() -> None:
    messages = [
        HumanMessage("first question"),
        AIMessage("first answer"),
        HumanMessage("second question"),
    ]

    assert _last_user_text({"messages": messages}) == "second question"  # type: ignore[typeddict-item]


def test_last_user_text_ignores_system_and_ai_messages() -> None:
    messages = [
        SystemMessage("system prompt"),
        HumanMessage("the actual question"),
        AIMessage("an answer"),
    ]

    assert _last_user_text({"messages": messages}) == "the actual question"  # type: ignore[typeddict-item]


def test_last_user_text_raises_when_no_human_message() -> None:
    messages = [SystemMessage("system prompt"), AIMessage("an answer")]

    with pytest.raises(ValueError, match="No user message"):
        _last_user_text({"messages": messages})  # type: ignore[typeddict-item]
