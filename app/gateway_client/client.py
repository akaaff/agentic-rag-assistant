from __future__ import annotations

from datetime import datetime

import httpx

from app.config import settings
from app.gateway_client.models import (
    LoginResponse,
    OrderResponse,
    OrderSearchDocument,
    OrderStatus,
)


class GatewayClient:
    """Read-only HTTP client for order-fulfillment-platform's gateway.

    Exactly three methods exist - login, get_order, search_orders - because
    that's the entire surface this assistant is allowed to touch. There is
    no cancel/update method here, and none should ever be added: the
    gateway's own API doesn't expose one, and this assistant's whole
    security posture (see docs_corpus/cancellation-policy.md) depends on it
    being *unable* to act on a customer's behalf, not merely instructed not
    to - the same boundary the sibling repo's OrderTools enforces by never
    giving the model a customerId parameter to control.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.order_platform_gateway_url).rstrip("/")

    async def login(self, customer_id: str) -> LoginResponse:
        """POST /auth/login. Raises httpx.HTTPStatusError (401) for a
        customer_id outside the 5 seeded demo ids."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self._base_url}/auth/login", json={"customerId": customer_id}
            )
            response.raise_for_status()
        return LoginResponse.model_validate(response.json())

    async def get_order(self, order_id: str, token: str) -> OrderResponse | None:
        """GET /api/orders/{orderId}. Returns None on 404 - which the
        gateway returns identically for "doesn't exist" and "exists but
        belongs to someone else", so this client can't distinguish them
        either, by design (no info leak about other customers' orders)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self._base_url}/api/orders/{order_id}",
                headers=_auth_header(token),
            )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return OrderResponse.model_validate(response.json())

    async def search_orders(
        self,
        token: str,
        status: OrderStatus | None = None,
        from_: datetime | None = None,
        to: datetime | None = None,
    ) -> list[OrderSearchDocument]:
        """GET /api/orders/search. No customer_id parameter - scoping comes
        entirely from the JWT server-side, same as the underlying API."""
        params: dict[str, str] = {}
        if status is not None:
            params["status"] = status.value
        if from_ is not None:
            params["from"] = from_.isoformat()
        if to is not None:
            params["to"] = to.isoformat()

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self._base_url}/api/orders/search",
                params=params,
                headers=_auth_header(token),
            )
            response.raise_for_status()
        return [OrderSearchDocument.model_validate(item) for item in response.json()]


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
