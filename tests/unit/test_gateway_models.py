from app.gateway_client.models import (
    LoginResponse,
    OrderResponse,
    OrderSearchDocument,
    OrderStatus,
)

# Fixture JSON shaped exactly like the real gateway's responses (see
# order-fulfillment-platform's OrderResponse.java / OrderSearchDocument.java)
# - camelCase, cancellationReason only present on cancelled orders.

ORDER_RESPONSE_JSON = {
    "orderId": "8f14e45f-ceea-467e-adde-3f4edbca85e1",
    "customerId": "cust-001",
    "lines": [{"sku": "WIDGET-1", "quantity": 2}],
    "status": "PENDING",
    "cancellationReason": None,
    "createdAt": "2026-08-18T10:00:00Z",
}

CANCELLED_ORDER_RESPONSE_JSON = {
    "orderId": "8f14e45f-ceea-467e-adde-3f4edbca85e1",
    "customerId": "cust-001",
    "lines": [{"sku": "WIDGET-1", "quantity": 2}],
    "status": "CANCELLED",
    "cancellationReason": "insufficient stock for WIDGET-1",
    "createdAt": "2026-08-18T10:00:00Z",
}

ORDER_SEARCH_DOCUMENT_JSON = {
    "orderId": "8f14e45f-ceea-467e-adde-3f4edbca85e1",
    "customerId": "cust-001",
    "status": "CONFIRMED",
    "skus": ["WIDGET-1", "WIDGET-2"],
    "cancellationReason": None,
    "createdAt": "2026-08-18T10:00:00Z",
    "updatedAt": "2026-08-18T10:05:00Z",
}

LOGIN_RESPONSE_JSON = {
    "token": "eyJhbGciOiJSUzI1NiJ9.fake.token",
    "customerId": "cust-001",
    "expiresAt": "2026-08-18T11:00:00Z",
}


def test_order_response_parses_camel_case_json() -> None:
    order = OrderResponse.model_validate(ORDER_RESPONSE_JSON)

    assert str(order.order_id) == ORDER_RESPONSE_JSON["orderId"]
    assert order.customer_id == "cust-001"
    assert order.status == OrderStatus.PENDING
    assert order.lines[0].sku == "WIDGET-1"
    assert order.lines[0].quantity == 2
    assert order.cancellation_reason is None


def test_order_response_carries_cancellation_reason() -> None:
    order = OrderResponse.model_validate(CANCELLED_ORDER_RESPONSE_JSON)

    assert order.status == OrderStatus.CANCELLED
    assert order.cancellation_reason == "insufficient stock for WIDGET-1"


def test_order_search_document_parses_camel_case_json() -> None:
    doc = OrderSearchDocument.model_validate(ORDER_SEARCH_DOCUMENT_JSON)

    assert doc.customer_id == "cust-001"
    assert doc.status == OrderStatus.CONFIRMED
    assert doc.skus == ["WIDGET-1", "WIDGET-2"]
    assert doc.updated_at > doc.created_at


def test_login_response_parses_camel_case_json() -> None:
    login = LoginResponse.model_validate(LOGIN_RESPONSE_JSON)

    assert login.token.startswith("eyJ")
    assert login.customer_id == "cust-001"


def test_order_status_only_has_three_values() -> None:
    # There is no SHIPPED/DELIVERED - this is a live-verified fact about the
    # sibling repo's domain model, not an assumption. See DECISIONS.md.
    assert {s.value for s in OrderStatus} == {"PENDING", "CONFIRMED", "CANCELLED"}
