import uuid

import httpx
import pytest

from app.gateway_client.client import GatewayClient

pytestmark = pytest.mark.integration


@pytest.fixture
def client() -> GatewayClient:
    return GatewayClient()


async def test_login_returns_token_for_known_customer(client: GatewayClient) -> None:
    login = await client.login("cust-001")

    assert login.token
    assert login.customer_id == "cust-001"


async def test_login_rejects_unknown_customer(client: GatewayClient) -> None:
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await client.login("not-a-real-customer")

    assert exc_info.value.response.status_code == 401


async def test_get_order_returns_none_for_nonexistent_order(client: GatewayClient) -> None:
    login = await client.login("cust-001")

    order = await client.get_order(str(uuid.uuid4()), login.token)

    assert order is None


async def test_search_orders_only_returns_own_orders(client: GatewayClient) -> None:
    login = await client.login("cust-001")

    results = await client.search_orders(login.token)

    assert all(r.customer_id == "cust-001" for r in results)
