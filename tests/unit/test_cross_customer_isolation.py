import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.nodes.tools import tools_node
from app.gateway_client.models import OrderResponse
from tests.unit.fakes import FakeChatModel

CUST_002_ORDER_ID = "11111111-1111-1111-1111-111111111111"


class _CrossCustomerGatewayClient:
    """Mimics the real gateway's documented behavior (verified live during
    Day 1's exploration of order-fulfillment-platform): GET /orders/{id}
    returns 404 - modeled here as None - identically whether the order
    doesn't exist or belongs to a different customer. Only order_id is
    checked; the token is accepted but irrelevant to this fake, exactly
    like the real endpoint scopes server-side from the JWT, never from
    anything the caller supplies alongside it."""

    async def get_order(self, order_id: str, token: str) -> OrderResponse | None:
        if order_id == CUST_002_ORDER_ID:
            return None
        raise AssertionError(f"unexpected order_id in test: {order_id}")

    async def search_orders(
        self, token: str, status: object = None, from_: object = None, to: object = None
    ) -> list[object]:
        return []


async def test_tools_node_cannot_leak_another_customers_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even if the model is tricked (injection, hallucination, or a crafted
    tool-call argument) into looking up another customer's order ID, the
    gateway's own server-side JWT scoping - not anything in this repo's own
    logic - is what actually blocks it. This test confirms our tool wrapper
    surfaces that as a clean "not found", never a leak."""
    tool_call_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_order_status",
                "args": {"order_id": CUST_002_ORDER_ID},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )
    fake_llm = FakeChatModel([tool_call_response])
    monkeypatch.setattr("app.agent.nodes.tools.get_chat_model", lambda: fake_llm)
    monkeypatch.setattr("app.agent.nodes.tools.GatewayClient", _CrossCustomerGatewayClient)

    state = {
        "messages": [HumanMessage(f"What's the status of order {CUST_002_ORDER_ID}?")],
        "customer_jwt": "jwt-for-cust-001",
        "tool_call_count": 0,
    }
    result = await tools_node(state)  # type: ignore[arg-type]

    tool_message = result["messages"][1]
    assert "not found" in tool_message.content.lower()


async def test_tools_node_ignores_model_supplied_customer_id_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_order_status's tool schema only declares order_id. If the model
    somehow emits an extra customer_id argument (hallucination or an
    injection attempt), LangChain's tool-argument binding silently drops
    unexpected keys (verified directly against @tool before writing this
    test) - it never reaches the tool function, and customer identity still
    only ever flows through the customer_jwt closure."""

    class _RecordingGatewayClient:
        received_order_id: str | None = None

        async def get_order(self, order_id: str, token: str) -> OrderResponse | None:
            _RecordingGatewayClient.received_order_id = order_id
            return None

        async def search_orders(
            self, token: str, status: object = None, from_: object = None, to: object = None
        ) -> list[object]:
            return []

    tool_call_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_order_status",
                "args": {"order_id": "some-order", "customer_id": "cust-002"},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )
    fake_llm = FakeChatModel([tool_call_response])
    monkeypatch.setattr("app.agent.nodes.tools.get_chat_model", lambda: fake_llm)
    monkeypatch.setattr("app.agent.nodes.tools.GatewayClient", _RecordingGatewayClient)

    state = {
        "messages": [HumanMessage("q")],
        "customer_jwt": "jwt-for-cust-001",
        "tool_call_count": 0,
    }
    result = await tools_node(state)  # type: ignore[arg-type]

    assert _RecordingGatewayClient.received_order_id == "some-order"
    assert result["tool_call_count"] == 1
