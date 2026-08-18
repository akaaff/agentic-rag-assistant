import httpx
import pytest

from app.config import settings


@pytest.fixture(scope="session", autouse=True)
def _require_order_platform_gateway() -> None:
    """Skip every integration test if order-fulfillment-platform's gateway
    isn't running, rather than failing with a raw connection-error
    traceback. Any HTTP response (even an error status) proves something is
    listening; only a transport-level failure means "not running" - on this
    machine an unclaimed localhost port times out rather than refusing the
    connection outright, so this catches httpx.TransportError broadly
    (ConnectError, ConnectTimeout, etc.), not just ConnectError."""
    try:
        httpx.get(f"{settings.order_platform_gateway_url}/auth/login", timeout=2.0)
    except httpx.TransportError:
        pytest.skip(
            f"order-fulfillment-platform gateway not reachable at "
            f"{settings.order_platform_gateway_url} - start it to run integration tests"
        )
