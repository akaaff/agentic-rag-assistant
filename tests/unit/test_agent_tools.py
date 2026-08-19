import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.nodes.tools import tools_node
from app.gateway_client.models import OrderResponse, OrderStatus
from tests.unit.fakes import FakeChatModel

ORDER_ID = "8f14e45f-ceea-467e-adde-3f4edbca85e1"


class _FakeGatewayClient:
    """Records (order_id, token) at the class level, since build_tools()
    constructs its own GatewayClient() instance internally that tests have
    no direct reference to. Lets tests assert the JWT binding actually
    happened - not just that a tool ran - by checking the token the fake
    received matches the one from state, not something model-supplied."""

    calls: list[tuple[str, str]] = []

    async def get_order(self, order_id: str, token: str) -> OrderResponse | None:
        _FakeGatewayClient.calls.append((order_id, token))
        return OrderResponse.model_validate(
            {
                "orderId": ORDER_ID,
                "customerId": "cust-001",
                "lines": [],
                "status": "CANCELLED",
                "cancellationReason": "insufficient stock",
                "createdAt": "2026-08-18T10:00:00Z",
            }
        )

    async def search_orders(
        self, token: str, status: OrderStatus | None = None, from_: object = None, to: object = None
    ) -> list[object]:
        return []


async def test_tools_node_executes_tool_call_and_binds_jwt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_call_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_order_status",
                "args": {"order_id": ORDER_ID},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )
    fake_llm = FakeChatModel([tool_call_response])
    monkeypatch.setattr("app.agent.nodes.tools.get_chat_model", lambda: fake_llm)
    monkeypatch.setattr("app.agent.nodes.tools.GatewayClient", _FakeGatewayClient)
    _FakeGatewayClient.calls = []

    state = {
        "messages": [HumanMessage("Why was my order cancelled?")],
        "customer_jwt": "fake-jwt-for-cust-001",
        "tool_call_count": 0,
    }
    result = await tools_node(state)  # type: ignore[arg-type]

    # The model only ever supplied order_id; the token came from state, not
    # from anything the model controlled - this is the actual security
    # boundary being tested, not just "did a tool run".
    assert _FakeGatewayClient.calls == [(ORDER_ID, "fake-jwt-for-cust-001")]

    assert result["tool_call_count"] == 1
    assert result["needs_more_tools"] is True

    new_messages = result["messages"]
    assert new_messages[0] is tool_call_response
    tool_message = new_messages[1]
    assert isinstance(tool_message, ToolMessage)
    assert "CANCELLED" in tool_message.content
    assert "insufficient stock" in tool_message.content


async def test_tools_node_stops_when_model_calls_no_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plain_response = AIMessage(content="I already have enough info.")
    fake_llm = FakeChatModel([plain_response])
    monkeypatch.setattr("app.agent.nodes.tools.get_chat_model", lambda: fake_llm)
    monkeypatch.setattr("app.agent.nodes.tools.GatewayClient", _FakeGatewayClient)

    state = {
        "messages": [HumanMessage("q")],
        "customer_jwt": "fake-jwt",
        "tool_call_count": 0,
    }
    result = await tools_node(state)  # type: ignore[arg-type]

    assert result == {"needs_more_tools": False}
