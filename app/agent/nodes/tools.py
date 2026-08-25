from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, tool

from app.agent.llm import get_chat_model
from app.agent.prompts.tools import TOOLS_SYSTEM_PROMPT
from app.agent.state import GraphState
from app.gateway_client.client import GatewayClient
from app.gateway_client.models import OrderStatus


def build_tools(customer_jwt: str) -> list[BaseTool]:
    """Tools closed over customer_jwt, captured once per graph invocation.

    The model can supply order_id/status as arguments, but never whose
    orders it's looking up - customer_jwt is bound here, not exposed as a
    parameter the model could set. Same boundary the sibling repo's
    OrderTools enforces (customerId captured at construction, never a
    model-controllable field), and the same reason a successful prompt
    injection could only ever change *which* order is queried, never
    *whose* orders are visible.
    """
    gateway = GatewayClient()

    @tool
    async def get_order_status(order_id: str) -> str:
        """Get the status of one of the caller's own orders by its order ID."""
        order = await gateway.get_order(order_id, customer_jwt)
        if order is None:
            return f"Order {order_id} not found."
        reason = f" (reason: {order.cancellation_reason})" if order.cancellation_reason else ""
        return (
            f"Order {order.order_id} is {order.status.value}{reason}, "
            f"placed {order.created_at.isoformat()}."
        )

    @tool
    async def search_my_orders(status: str | None = None) -> str:
        """Search the caller's own orders, optionally filtered by status
        (PENDING, CONFIRMED, or CANCELLED). Leave blank to list all."""
        # status is typed str, not OrderStatus, deliberately: verified live
        # that qwen2.5:7b-instruct sometimes calls this with status="" (an
        # empty string, meaning "no filter") rather than omitting the
        # argument entirely. An OrderStatus-typed parameter rejects that at
        # LangChain's schema-validation layer *before* this function body
        # ever runs, crashing the whole tools_node with an unhandled
        # pydantic ValidationError mid-request - so the coercion has to
        # happen here, not in the type annotation. A genuinely-invalid
        # value (neither empty nor a real status) gets a message the model
        # can react to instead of a crash.
        status_enum: OrderStatus | None = None
        if status:
            try:
                status_enum = OrderStatus(status)
            except ValueError:
                return (
                    f"'{status}' isn't a valid status - use PENDING, CONFIRMED, or CANCELLED, "
                    "or leave it blank to list all orders."
                )
        results = await gateway.search_orders(customer_jwt, status=status_enum)
        if not results:
            return "No matching orders found."
        lines = [f"- {r.order_id}: {r.status.value}" for r in results]
        return "Found orders:\n" + "\n".join(lines)

    return [get_order_status, search_my_orders]


async def tools_node(state: GraphState) -> dict[str, Any]:
    tools = build_tools(state["customer_jwt"])
    tools_by_name = {t.name: t for t in tools}
    llm = get_chat_model().bind_tools(tools)

    response = await llm.ainvoke([SystemMessage(TOOLS_SYSTEM_PROMPT), *state["messages"]])

    if not isinstance(response, AIMessage) or not response.tool_calls:
        # The model decided it has enough already - don't add this bare
        # response to history (answer_node produces the real final message
        # with its own prompt/formatting); just signal the loop is done.
        return {"needs_more_tools": False}

    tool_messages: list[ToolMessage] = []
    for call in response.tool_calls:
        tool_fn = tools_by_name[call["name"]]
        result = await tool_fn.ainvoke(call["args"])
        tool_messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    return {
        "messages": [response, *tool_messages],
        "tool_call_count": state["tool_call_count"] + 1,
        "needs_more_tools": True,
    }
