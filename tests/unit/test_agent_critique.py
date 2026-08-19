import pytest
from langchain_core.messages import HumanMessage

from app.agent.nodes.critique import CritiqueVerdict, critique_node
from tests.unit.fakes import FakeChatModel


async def test_critique_node_maps_grounded_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeChatModel([CritiqueVerdict(grounded=True)])
    monkeypatch.setattr("app.agent.nodes.critique.get_chat_model", lambda: fake)

    state = {"messages": [HumanMessage("q")], "retrieved_docs": []}
    result = await critique_node(state)  # type: ignore[arg-type]

    assert result == {"critique_verdict": "grounded"}


async def test_critique_node_maps_ungrounded_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeChatModel([CritiqueVerdict(grounded=False)])
    monkeypatch.setattr("app.agent.nodes.critique.get_chat_model", lambda: fake)

    state = {"messages": [HumanMessage("q")], "retrieved_docs": []}
    result = await critique_node(state)  # type: ignore[arg-type]

    assert result == {"critique_verdict": "ungrounded"}
