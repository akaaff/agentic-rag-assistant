import pytest
from langchain_core.messages import HumanMessage

from app.agent.nodes.router import RouteDecision, router_node
from tests.unit.fakes import FakeChatModel


async def test_router_node_extracts_decision_from_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeChatModel([RouteDecision(needs_retrieval=True, needs_tools=False)])
    monkeypatch.setattr("app.agent.nodes.router.get_chat_model", lambda: fake)

    state = {"messages": [HumanMessage("What's your return policy?")]}
    result = await router_node(state)  # type: ignore[arg-type]

    assert result == {"needs_retrieval": True, "needs_tools": False}


async def test_router_node_handles_both_flags_true(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeChatModel([RouteDecision(needs_retrieval=True, needs_tools=True)])
    monkeypatch.setattr("app.agent.nodes.router.get_chat_model", lambda: fake)

    state = {"messages": [HumanMessage("Is my pending order normal?")]}
    result = await router_node(state)  # type: ignore[arg-type]

    assert result == {"needs_retrieval": True, "needs_tools": True}
