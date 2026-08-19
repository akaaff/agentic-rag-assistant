import httpx
import pytest

from app.config import settings


@pytest.fixture(scope="session", autouse=True)
def _require_ollama() -> None:
    """Skip every test in this directory if Ollama isn't reachable, rather
    than failing with a raw connection error. Deliberately separate from
    tests/integration's gateway-reachability check (marker: integration) -
    these tests need only Ollama, which can easily be up while
    order-fulfillment-platform's much heavier stack is down (the normal
    state during this build)."""
    try:
        httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0)
    except httpx.TransportError:
        pytest.skip(f"Ollama not reachable at {settings.ollama_base_url}")
